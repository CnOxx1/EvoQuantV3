"""governance_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.governance_data.client import GovernanceDataClient


class GovernanceDataService:
    """DAO 治理数据采集与分析服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or GovernanceDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS governance_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                title TEXT DEFAULT '',
                state TEXT DEFAULT '',
                votes_for REAL DEFAULT 0,
                votes_against REAL DEFAULT 0,
                quorum_pct REAL DEFAULT 0,
                start_ts TEXT DEFAULT '',
                end_ts TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, proposal_id)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS governance_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                voter TEXT NOT NULL,
                voting_power REAL DEFAULT 0,
                choice TEXT DEFAULT '',
                timestamp TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, proposal_id, voter)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS governance_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                proposals_active INTEGER DEFAULT 0,
                participation_rate REAL DEFAULT 0,
                whale_vote_pct REAL DEFAULT 0,
                timestamp TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gov_proposals_protocol
            ON governance_proposals(protocol, state)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gov_votes_proposal
            ON governance_votes(protocol, proposal_id)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gov_activity_ts
            ON governance_activity(protocol, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("governance_data 存储初始化完成")

    def bootstrap(self):
        """首次回填：采集所有追踪空间的治理数据。"""
        logger.info("开始 governance_data bootstrap")
        self._collect_snapshot()
        self._collect_tally()
        self._compute_activity_metrics()
        logger.info("governance_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_snapshot()
        self._collect_tally()
        self._compute_activity_metrics()
        logger.info("governance_data collect_once 完成")

    def _collect_snapshot(self):
        """从 Snapshot 采集链下治理提案和投票数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        for space in self.client.TRACKED_SPACES:
            proposals = self.client.fetch_snapshot_proposals(space, state="active")
            proposals += self.client.fetch_snapshot_proposals(space, state="closed", first=5)

            if not proposals:
                logger.debug(f"Snapshot {space} 无提案数据")
                continue

            for p in proposals:
                proposal_id = p.get("id", "")
                if not proposal_id:
                    continue

                scores = p.get("scores", [])
                votes_for = scores[0] if len(scores) > 0 else 0.0
                votes_against = scores[1] if len(scores) > 1 else 0.0
                scores_total = p.get("scores_total", 0) or 0
                quorum = p.get("quorum", 0) or 0
                quorum_pct = (scores_total / quorum * 100) if quorum > 0 else 0.0

                self.db.conn.execute("""
                    INSERT OR REPLACE INTO governance_proposals
                    (protocol, proposal_id, title, state, votes_for, votes_against,
                     quorum_pct, start_ts, end_ts, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (space, proposal_id, p.get("title", ""),
                      p.get("state", ""), votes_for, votes_against,
                      round(quorum_pct, 2),
                      str(p.get("start", "")), str(p.get("end", "")),
                      now_iso))

                # 采集该提案的投票记录
                votes = self.client.fetch_snapshot_votes(proposal_id, first=100)
                for v in votes:
                    voter = v.get("voter", "")
                    if not voter:
                        continue
                    choice_raw = v.get("choice", "")
                    choice = str(choice_raw)
                    self.db.conn.execute("""
                        INSERT OR REPLACE INTO governance_votes
                        (protocol, proposal_id, voter, voting_power, choice,
                         timestamp, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (space, proposal_id, voter,
                          float(v.get("vp", 0)),
                          choice, str(v.get("created", "")),
                          now_iso))

            self.db.conn.commit()
            logger.info(f"Snapshot {space} 采集完成，{len(proposals)} 个提案")

    def _collect_tally(self):
        """从 Tally 采集链上治理提案数据。"""
        if not self.client.tally_key:
            logger.debug("Tally API key 未配置，跳过链上治理采集")
            return

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # Tally 使用 governor ID 而非 space 名称
        # 这里使用协议名称作为标识
        tally_governors = {
            "aave-onchain": "eip155:1:0xEC568fffba86c094cf06b22134B23074DFE2252c",
            "uniswap-onchain": "eip155:1:0x408ED6354d4973f66138C91495F2f2FCbd8724C3",
            "compound-onchain": "eip155:1:0xc0Da02939E1441F497fd74F78cE7Decb17B66529",
        }

        for protocol, governor_id in tally_governors.items():
            proposals = self.client.fetch_tally_proposals(governor_id, first=10)

            if not proposals:
                logger.debug(f"Tally {protocol} 无提案数据")
                continue

            for p in proposals:
                proposal_id = p.get("id", "")
                if not proposal_id:
                    continue

                # 解析投票统计
                vote_stats = p.get("voteStats", [])
                votes_for = 0.0
                votes_against = 0.0
                for vs in vote_stats:
                    support = vs.get("support", "")
                    count = float(vs.get("votesCount", 0) or 0)
                    if support == "FOR":
                        votes_for = count
                    elif support == "AGAINST":
                        votes_against = count

                # 解析状态
                status_changes = p.get("statusChanges", [])
                state = status_changes[-1].get("type", "unknown") if status_changes else "unknown"

                # 解析时间
                start_block = p.get("start", {}) or {}
                end_block = p.get("end", {}) or {}
                start_ts = start_block.get("timestamp", "")
                end_ts = end_block.get("timestamp", "")

                self.db.conn.execute("""
                    INSERT OR REPLACE INTO governance_proposals
                    (protocol, proposal_id, title, state, votes_for, votes_against,
                     quorum_pct, start_ts, end_ts, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (protocol, proposal_id, p.get("title", ""),
                      state, votes_for, votes_against,
                      0.0, start_ts, end_ts, now_iso))

                # 采集投票记录
                votes = self.client.fetch_tally_votes(proposal_id, first=100)
                for v in votes:
                    voter_obj = v.get("voter", {}) or {}
                    voter = voter_obj.get("address", "")
                    if not voter:
                        continue
                    block_info = v.get("block", {}) or {}
                    self.db.conn.execute("""
                        INSERT OR REPLACE INTO governance_votes
                        (protocol, proposal_id, voter, voting_power, choice,
                         timestamp, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (protocol, proposal_id, voter,
                          float(v.get("weight", 0) or 0),
                          v.get("support", ""),
                          block_info.get("timestamp", ""),
                          now_iso))

            self.db.conn.commit()
            logger.info(f"Tally {protocol} 采集完成，{len(proposals)} 个提案")

    def _compute_activity_metrics(self):
        """计算各协议的治理活跃度指标（参与率、巨鲸投票占比）。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取所有协议
        cursor = self.db.conn.execute("""
            SELECT DISTINCT protocol FROM governance_proposals
        """)
        protocols = [row[0] for row in cursor.fetchall()]

        for protocol in protocols:
            # 活跃提案数
            cursor = self.db.conn.execute("""
                SELECT COUNT(*) FROM governance_proposals
                WHERE protocol = ? AND state = 'active'
            """, (protocol,))
            proposals_active = cursor.fetchone()[0]

            # 参与率：有投票的提案占比
            cursor = self.db.conn.execute("""
                SELECT COUNT(*) FROM governance_proposals
                WHERE protocol = ?
            """, (protocol,))
            total_proposals = cursor.fetchone()[0]

            cursor = self.db.conn.execute("""
                SELECT COUNT(DISTINCT proposal_id) FROM governance_votes
                WHERE protocol = ?
            """, (protocol,))
            proposals_with_votes = cursor.fetchone()[0]

            participation_rate = (
                proposals_with_votes / total_proposals * 100
                if total_proposals > 0 else 0.0
            )

            # 巨鲸投票占比：前10%投票者的投票权重占总权重比例
            cursor = self.db.conn.execute("""
                SELECT voting_power FROM governance_votes
                WHERE protocol = ?
                ORDER BY voting_power DESC
            """, (protocol,))
            all_powers = [row[0] for row in cursor.fetchall()]

            whale_vote_pct = 0.0
            if all_powers:
                total_power = sum(all_powers)
                whale_count = max(1, len(all_powers) // 10)
                whale_power = sum(all_powers[:whale_count])
                whale_vote_pct = (
                    whale_power / total_power * 100
                    if total_power > 0 else 0.0
                )

            self.db.conn.execute("""
                INSERT OR REPLACE INTO governance_activity
                (protocol, proposals_active, participation_rate,
                 whale_vote_pct, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (protocol, proposals_active,
                  round(participation_rate, 2),
                  round(whale_vote_pct, 2),
                  now_iso, now_iso))

        self.db.conn.commit()
        logger.info(f"治理活跃度指标计算完成，涉及 {len(protocols)} 个协议")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的治理上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 活跃提案摘要
        cursor = self.db.conn.execute("""
            SELECT protocol, proposal_id, title, state, votes_for, votes_against,
                   quorum_pct, start_ts, end_ts
            FROM governance_proposals
            WHERE state = 'active'
            ORDER BY collected_at DESC
            LIMIT 20
        """)
        active_proposals = []
        for row in cursor.fetchall():
            active_proposals.append({
                "protocol": row[0],
                "proposal_id": row[1],
                "title": row[2],
                "state": row[3],
                "votes_for": round(row[4], 2),
                "votes_against": round(row[5], 2),
                "quorum_pct": round(row[6], 2),
                "start_ts": row[7],
                "end_ts": row[8],
            })

        if not active_proposals:
            return {"status": "no_data", "as_of": now_iso}

        # 参与率趋势
        cursor = self.db.conn.execute("""
            SELECT protocol, proposals_active, participation_rate, whale_vote_pct
            FROM governance_activity
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        activity_rows = cursor.fetchall()
        participation_trends = []
        for row in activity_rows:
            participation_trends.append({
                "protocol": row[0],
                "proposals_active": row[1],
                "participation_rate": round(row[2], 2),
                "whale_vote_pct": round(row[3], 2),
            })

        # 巨鲸投票模式分析
        cursor = self.db.conn.execute("""
            SELECT protocol, AVG(whale_vote_pct) as avg_whale_pct
            FROM governance_activity
            GROUP BY protocol
        """)
        whale_patterns = {}
        for row in cursor.fetchall():
            avg_pct = round(row[1], 2)
            whale_patterns[row[0]] = {
                "avg_whale_vote_pct": avg_pct,
                "concentration": "high" if avg_pct > 60 else (
                    "moderate" if avg_pct > 35 else "low"
                ),
            }

        # 整体治理健康度评估
        avg_participation = (
            sum(t["participation_rate"] for t in participation_trends)
            / len(participation_trends)
            if participation_trends else 0
        )
        avg_whale = (
            sum(t["whale_vote_pct"] for t in participation_trends)
            / len(participation_trends)
            if participation_trends else 0
        )

        governance_health = "healthy" if avg_participation > 50 and avg_whale < 50 else (
            "concentrated" if avg_whale > 60 else "low_engagement"
        )

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "governance_health": governance_health,
                "active_proposal_count": len(active_proposals),
                "avg_participation_rate": round(avg_participation, 2),
                "avg_whale_concentration": round(avg_whale, 2),
            },
            "active_proposals": active_proposals,
            "participation_trends": participation_trends,
            "whale_voting_patterns": whale_patterns,
            "interpretation": {
                "health": f"治理健康度: {governance_health}",
                "participation": f"平均参与率: {avg_participation:.1f}%",
                "whale": f"巨鲸投票集中度: {avg_whale:.1f}%",
                "active": f"当前活跃提案数: {len(active_proposals)}",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="governance_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="governance_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
