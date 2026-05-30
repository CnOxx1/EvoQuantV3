from datetime import timedelta

from loguru import logger

from config.settings import ALTERNATIVE_CONFIG
from data_layer.alternative_data.base import AlternativeCollectorBase
from data_layer.alternative_data.client import AlternativeDataClient, GitHubRateLimitExceededError
from data_layer.alternative_data.models import AlternativeTimeSeriesPoint, dump_json, utc_now_naive
from data_layer.alternative_data.sources import load_alternative_factors, load_github_repo_groups


class GitHubActivityCollector(AlternativeCollectorBase):
    """采集 repo group 级 GitHub 活跃度指标。"""

    def __init__(self, client: AlternativeDataClient, db):
        super().__init__(db)
        self.client = client

    @staticmethod
    def _extract_actor_identity(commit_payload: dict) -> str | None:
        author = commit_payload.get("author") or {}
        if isinstance(author, dict):
            login = (author.get("login") or "").strip()
            if login:
                return login.lower()

        commit = commit_payload.get("commit") or {}
        commit_author = commit.get("author") or {}
        for key in ("email", "name"):
            value = (commit_author.get(key) or "").strip()
            if value:
                return value.lower()
        return None

    @staticmethod
    def _quality_flag(success_count: int, total_count: int) -> str:
        if total_count <= 0 or success_count >= total_count:
            return "ok"
        if success_count == 0:
            return "fallback"
        return "partial"

    @staticmethod
    def _parse_repo(repo_full_name: str) -> tuple[str, str]:
        owner, repo = repo_full_name.split("/", 1)
        return owner, repo

    @staticmethod
    def _build_point(
        factor,
        entity_key: str,
        observation_time,
        value: float,
        quality_flag: str,
        dimensions_json: dict[str, object],
        source_symbol: str,
        raw_payload: dict[str, object],
    ) -> AlternativeTimeSeriesPoint:
        return AlternativeTimeSeriesPoint(
            factor_id=factor.factor_id,
            category=factor.category,
            factor_type=factor.factor_type,
            entity_type=factor.entity_type,
            entity_key=entity_key,
            interval=factor.default_interval,
            observation_time=observation_time,
            value=float(value),
            unit=factor.unit,
            quality_flag=quality_flag,
            dimensions_json=dimensions_json,
            config_version=factor.config_version,
            source_name=factor.source_name,
            source_symbol=source_symbol,
            raw_payload_json=dump_json(raw_payload),
        )

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        factor_map = {
            factor.factor_id: factor
            for factor in load_alternative_factors(source_names=["github"])
        }
        repo_groups = load_github_repo_groups(entity_keys=entity_keys)
        if not repo_groups:
            return []

        observation_time = utc_now_naive()
        repo_group_version = ALTERNATIVE_CONFIG["github_repo_group_version"]
        results: list[AlternativeTimeSeriesPoint] = []
        hit_rate_limit = False

        for group in repo_groups:
            repos = [str(repo) for repo in group.get("repos", [])]
            if not repos:
                continue

            commits_1d_total = 0
            commits_7d_total = 0
            active_contributors: set[str] = set()
            opened_pr_count_7d = 0
            merged_pr_count_7d = 0
            release_count_30d = 0
            repo_details: dict[str, object] = {}
            success_count = 0

            for repo_full_name in repos:
                owner, repo = self._parse_repo(repo_full_name)
                try:
                    commits_1d = self.client.fetch_github_commits(
                        owner=owner,
                        repo=repo,
                        since=observation_time - timedelta(days=1),
                        until=observation_time,
                    )
                    commits_7d = self.client.fetch_github_commits(
                        owner=owner,
                        repo=repo,
                        since=observation_time - timedelta(days=7),
                        until=observation_time,
                    )
                    opened_prs = self.client.search_github_pull_request_count(
                        owner=owner,
                        repo=repo,
                        qualifier="created",
                        since=observation_time - timedelta(days=7),
                    )
                    merged_prs = self.client.search_github_pull_request_count(
                        owner=owner,
                        repo=repo,
                        qualifier="merged",
                        since=observation_time - timedelta(days=7),
                    )
                    releases = self.client.fetch_github_releases(owner=owner, repo=repo)
                except GitHubRateLimitExceededError as exc:
                    logger.warning(
                        f"GitHub repo group 采集命中 rate limit，提前结束当前采集轮次 "
                        f"[{group['entity_key']}] [{repo_full_name}]: {exc}"
                    )
                    repo_details[repo_full_name] = {"error": str(exc)}
                    hit_rate_limit = True
                    break
                except Exception as exc:
                    logger.warning(
                        f"GitHub repo group 子仓库采集失败 [{group['entity_key']}] "
                        f"[{repo_full_name}]: {exc}"
                    )
                    repo_details[repo_full_name] = {"error": str(exc)}
                    continue

                success_count += 1
                commits_1d_total += len(commits_1d)
                commits_7d_total += len(commits_7d)
                active_contributors.update(
                    actor
                    for actor in (
                        self._extract_actor_identity(commit_payload)
                        for commit_payload in commits_7d
                    )
                    if actor
                )
                opened_pr_count_7d += opened_prs
                merged_pr_count_7d += merged_prs
                recent_releases = [
                    release
                    for release in releases
                    if AlternativeDataClient._parse_timestamp(
                        release.get("published_at") or release.get("created_at")
                    ) is not None
                    and AlternativeDataClient._parse_timestamp(
                        release.get("published_at") or release.get("created_at")
                    ) >= observation_time - timedelta(days=30)
                ]
                release_count_30d += len(recent_releases)
                repo_details[repo_full_name] = {
                    "commit_count_1d": len(commits_1d),
                    "commit_count_7d": len(commits_7d),
                    "opened_pr_count_7d": opened_prs,
                    "merged_pr_count_7d": merged_prs,
                    "release_count_30d": len(recent_releases),
                }

            quality_flag = self._quality_flag(success_count, len(repos))
            if success_count == 0:
                if hit_rate_limit:
                    break
                continue

            point_dimensions = {
                "repo_group_version": repo_group_version,
                "repo_count": len(repos),
            }
            source_symbol = f"repo_group:{group['entity_key']}"
            raw_payload = {
                "repo_group": group["name"],
                "repo_group_version": repo_group_version,
                "repos": repos,
                "repo_details": repo_details,
            }

            results.extend(
                [
                    self._build_point(
                        factor=factor_map["github_commit_count_1d"],
                        entity_key=str(group["entity_key"]),
                        observation_time=observation_time,
                        value=commits_1d_total,
                        quality_flag=quality_flag,
                        dimensions_json=point_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            **raw_payload,
                            "metric": "github_commit_count_1d",
                            "value": commits_1d_total,
                        },
                    ),
                    self._build_point(
                        factor=factor_map["github_commit_count_7d"],
                        entity_key=str(group["entity_key"]),
                        observation_time=observation_time,
                        value=commits_7d_total,
                        quality_flag=quality_flag,
                        dimensions_json=point_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            **raw_payload,
                            "metric": "github_commit_count_7d",
                            "value": commits_7d_total,
                        },
                    ),
                    self._build_point(
                        factor=factor_map["github_active_contributors_7d"],
                        entity_key=str(group["entity_key"]),
                        observation_time=observation_time,
                        value=len(active_contributors),
                        quality_flag=quality_flag,
                        dimensions_json=point_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            **raw_payload,
                            "metric": "github_active_contributors_7d",
                            "contributors": sorted(active_contributors),
                            "value": len(active_contributors),
                        },
                    ),
                    self._build_point(
                        factor=factor_map["github_opened_pr_count_7d"],
                        entity_key=str(group["entity_key"]),
                        observation_time=observation_time,
                        value=opened_pr_count_7d,
                        quality_flag=quality_flag,
                        dimensions_json=point_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            **raw_payload,
                            "metric": "github_opened_pr_count_7d",
                            "value": opened_pr_count_7d,
                        },
                    ),
                    self._build_point(
                        factor=factor_map["github_merged_pr_count_7d"],
                        entity_key=str(group["entity_key"]),
                        observation_time=observation_time,
                        value=merged_pr_count_7d,
                        quality_flag=quality_flag,
                        dimensions_json=point_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            **raw_payload,
                            "metric": "github_merged_pr_count_7d",
                            "value": merged_pr_count_7d,
                        },
                    ),
                    self._build_point(
                        factor=factor_map["github_release_count_30d"],
                        entity_key=str(group["entity_key"]),
                        observation_time=observation_time,
                        value=release_count_30d,
                        quality_flag=quality_flag,
                        dimensions_json=point_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            **raw_payload,
                            "metric": "github_release_count_30d",
                            "value": release_count_30d,
                        },
                    ),
                ]
            )

            if hit_rate_limit:
                break

        return results

    def bootstrap_history(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        return self.fetch_recent_points(entity_keys=entity_keys)

    def collect(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        logger.info("开始采集 GitHub repo group 活跃度...")
        points = self.fetch_recent_points(entity_keys=entity_keys)
        if points:
            self.save_to_db(points)
        logger.info(f"GitHub repo group 活跃度采集完成，共 {len(points)} 条")
        return points
