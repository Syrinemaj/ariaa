from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base
from app.db.mixins import TimestampMixin


class EndpointEmbedding(TimestampMixin, Base):
    """
    Stocke le vecteur d'embedding cosine pour chaque endpoint.

    Index HNSW (Hierarchical Navigable Small World) :
    - Remplace le scan O(n) par une recherche approximative O(log n)
    - m=16 : nombre de connexions par nœud (compromis mémoire/vitesse)
    - ef_construction=64 : qualité de la construction du graphe
    - vector_cosine_ops : distance cosine (aligné avec ADA-002 / text-embedding-3-small)
    - CONCURRENTLY dans la migration → création sans lock table
    """

    __tablename__ = "endpoint_embeddings"
    __table_args__ = (
        UniqueConstraint("endpoint_id", name="uq_endpoint_embedding_endpoint_id"),
        # HNSW index déclaré ici pour que les outils d'inspection ORM le voient.
        # La migration 005 le crée avec CONCURRENTLY pour éviter le lock.
        Index(
            "idx_endpoint_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    endpoint_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )
    embedding_text: Mapped[str] = mapped_column(String, nullable=False)
    embedding = mapped_column(
        Vector(settings.EMBEDDING_DIMENSIONS), nullable=False
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    endpoint = relationship("Endpoint")
