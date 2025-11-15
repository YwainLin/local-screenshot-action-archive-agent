from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    from neo4j import GraphDatabase

    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


class GraphStore:
    """Neo4j 图存储服务"""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
    ) -> None:
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None

        if NEO4J_AVAILABLE:
            try:
                self.driver = GraphDatabase.driver(uri, auth=(user, password))
            except Exception:
                self.driver = None

    @property
    def is_available(self) -> bool:
        return self.driver is not None

    def close(self) -> None:
        if self.driver:
            self.driver.close()

    def init_schema(self) -> None:
        """初始化图数据库 Schema"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (a:Asset) REQUIRE a.id IS UNIQUE
                """
            )
            session.run(
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (o:OcrChunk) REQUIRE o.id IS UNIQUE
                """
            )
            session.run(
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE
                """
            )
            session.run(
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (ai:ActionItem) REQUIRE ai.id IS UNIQUE
                """
            )
            session.run(
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (ap:ArchiveProposal) REQUIRE ap.id IS UNIQUE
                """
            )
            session.run(
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE
                """
            )

    def create_asset_node(self, asset_id: str, filename: str, path: str) -> None:
        """创建 Asset 节点"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (a:Asset {id: $asset_id})
                SET a.filename = $filename, a.path = $path
                """,
                asset_id=asset_id,
                filename=filename,
                path=path,
            )

    def create_ocr_chunk_node(
        self, chunk_id: str, asset_id: str, text: str, engine: str
    ) -> None:
        """创建 OcrChunk 节点并建立关系"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (o:OcrChunk {id: $chunk_id})
                SET o.text = $text, o.engine = $engine
                WITH o
                MATCH (a:Asset {id: $asset_id})
                MERGE (a)-[:HAS_OCR]->(o)
                """,
                chunk_id=chunk_id,
                text=text,
                engine=engine,
                asset_id=asset_id,
            )

    def create_entity_node(
        self,
        entity_id: str,
        kind: str,
        value: str,
        asset_id: str,
        confidence: float = 0.0,
        evidence_span: str = "",
        is_model_suggestion: bool = False,
    ) -> None:
        """创建 Entity 节点并建立关系"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (e:Entity {id: $entity_id})
                SET e.kind = $kind, e.value = $value, e.is_model_suggestion = $is_model_suggestion
                WITH e
                MATCH (a:Asset {id: $asset_id})
                MERGE (a)-[:MENTIONS {confidence: $confidence, evidence_span: $evidence_span}]->(e)
                """,
                entity_id=entity_id,
                kind=kind,
                value=value,
                is_model_suggestion=is_model_suggestion,
                asset_id=asset_id,
                confidence=confidence,
                evidence_span=evidence_span,
            )

    def create_action_item_node(
        self,
        action_id: str,
        asset_id: str,
        description: str,
        confidence: float = 0.0,
    ) -> None:
        """创建 ActionItem 节点并建立关系"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (ai:ActionItem {id: $action_id})
                SET ai.description = $description, ai.confidence = $confidence
                WITH ai
                MATCH (a:Asset {id: $asset_id})
                MERGE (a)-[:SUGGESTED_ACTION]->(ai)
                """,
                action_id=action_id,
                asset_id=asset_id,
                description=description,
                confidence=confidence,
            )

    def create_archive_proposal_node(
        self,
        proposal_id: str,
        action: str,
        target_category: str,
        rationale: str,
        confidence: float,
        action_id: str,
    ) -> None:
        """创建 ArchiveProposal 节点并建立关系"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (ap:ArchiveProposal {id: $proposal_id})
                SET ap.action = $action, ap.target_category = $target_category,
                    ap.rationale = $rationale, ap.confidence = $confidence
                WITH ap
                MATCH (ai:ActionItem {id: $action_id})
                MERGE (ai)-[:PROPOSES]->(ap)
                """,
                proposal_id=proposal_id,
                action=action,
                target_category=target_category,
                rationale=rationale,
                confidence=confidence,
                action_id=action_id,
            )

    def create_category_node(self, category_id: str, name: str) -> None:
        """创建 Category 节点并建立关系"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (c:Category {id: $category_id})
                SET c.name = $name
                WITH c
                MATCH (ap:ArchiveProposal {id: $proposal_id})
                MERGE (ap)-[:IN_CATEGORY]->(c)
                """,
                category_id=category_id,
                name=name,
            )

    def create_duplicate_relationship(
        self,
        asset_id_1: str,
        asset_id_2: str,
        kind: str,
        distance: int,
    ) -> None:
        """创建重复关系"""
        if not self.is_available:
            return

        with self.driver.session() as session:
            session.run(
                """
                MATCH (a1:Asset {id: $asset_id_1})
                MATCH (a2:Asset {id: $asset_id_2})
                MERGE (a1)-[:DUPLICATE_OF {kind: $kind, distance: $distance}]->(a2)
                """,
                asset_id_1=asset_id_1,
                asset_id_2=asset_id_2,
                kind=kind,
                distance=distance,
            )

    def get_asset_relationships(self, asset_id: str) -> Dict[str, Any]:
        """获取资产的所有关系"""
        if not self.is_available:
            return {}

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (a:Asset {id: $asset_id})
                OPTIONAL MATCH (a)-[r1:HAS_OCR]->(o:OcrChunk)
                OPTIONAL MATCH (a)-[r2:MENTIONS]->(e:Entity)
                OPTIONAL MATCH (a)-[r3:SUGGESTED_ACTION]->(ai:ActionItem)
                OPTIONAL MATCH (a)-[r4:DUPLICATE_OF]->(d:Asset)
                RETURN
                    collect(DISTINCT o.text) as ocr_texts,
                    collect(DISTINCT {kind: e.kind, value: e.value}) as entities,
                    collect(DISTINCT {description: ai.description, confidence: ai.confidence}) as actions,
                    collect(DISTINCT {id: d.id, filename: d.filename}) as duplicates
                """,
                asset_id=asset_id,
            )
            record = result.single()
            if record:
                return {
                    "ocr_texts": record["ocr_texts"],
                    "entities": record["entities"],
                    "actions": record["actions"],
                    "duplicates": record["duplicates"],
                }
            return {}

    def search_by_entity(
        self, entity_kind: str, entity_value: str
    ) -> List[Dict[str, Any]]:
        """通过实体搜索相关资产"""
        if not self.is_available:
            return []

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (a:Asset)-[:MENTIONS]->(e:Entity {kind: $kind})
                WHERE e.value CONTAINS $value
                RETURN a.id as asset_id, a.filename as filename, a.path as path
                LIMIT 50
                """,
                kind=entity_kind,
                value=entity_value,
            )
            return [dict(record) for record in result]

    def get_proposal_graph(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """获取归档建议的完整图结构"""
        if not self.is_available:
            return None

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (ap:ArchiveProposal {id: $proposal_id})
                OPTIONAL MATCH (ai)-[:PROPOSES]->(ap)
                OPTIONAL MATCH (a)-[:SUGGESTED_ACTION]->(ai)
                OPTIONAL MATCH (a)-[:MENTIONS]->(e:Entity)
                RETURN
                    ap {.*} as proposal,
                    ai {.*} as action_item,
                    a {id: a.id, filename: a.filename} as asset,
                    collect(DISTINCT {kind: e.kind, value: e.value}) as entities
                """,
                proposal_id=proposal_id,
            )
            record = result.single()
            if record:
                return {
                    "proposal": dict(record["proposal"]) if record["proposal"] else None,
                    "action_item": dict(record["action_item"]) if record["action_item"] else None,
                    "asset": dict(record["asset"]) if record["asset"] else None,
                    "entities": record["entities"],
                }
            return None


def get_graph_store(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "password",
) -> GraphStore:
    """获取图存储服务实例"""
    return GraphStore(uri=uri, user=user, password=password)
