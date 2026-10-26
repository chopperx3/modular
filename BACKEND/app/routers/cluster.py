from fastapi import APIRouter

from ..cluster import cluster

router = APIRouter(prefix="/cluster", tags=["cluster"])

@router.get("/status")
def cluster_status():
    """Workers conectados, su carga, la cola del coordinador y contadores de fallos/reasignaciones."""
    return cluster.status()
