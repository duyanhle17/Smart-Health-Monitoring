from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class TunnelEdge:
    """Undirected tunnel edge between two zones."""

    source: str
    target: str
    distance_m: float = 1.0


class MineTopology:
    """Simple mine graph to support feature engineering and routing."""

    def __init__(self, zones: Iterable[str], edges: Iterable[TunnelEdge]):
        self.zones = sorted({z for z in zones})
        self._adjacency: Dict[str, List[Tuple[str, float]]] = {z: [] for z in self.zones}

        for edge in edges:
            if edge.source not in self._adjacency or edge.target not in self._adjacency:
                raise ValueError(f"Edge refers to unknown zone: {edge}")
            self._adjacency[edge.source].append((edge.target, edge.distance_m))
            self._adjacency[edge.target].append((edge.source, edge.distance_m))

    @classmethod
    def from_json(cls, path: str) -> "MineTopology":
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        zones = payload.get("zones", [])
        raw_edges = payload.get("edges", [])

        edges = [
            TunnelEdge(
                source=str(item["source"]),
                target=str(item["target"]),
                distance_m=float(item.get("distance_m", 1.0)),
            )
            for item in raw_edges
        ]
        return cls(zones=zones, edges=edges)

    def neighbors(self, zone: str) -> List[Tuple[str, float]]:
        return list(self._adjacency.get(zone, []))

    def degree(self, zone: str) -> int:
        return len(self._adjacency.get(zone, []))

    def to_dict(self) -> dict:
        emitted_edges = []
        seen = set()
        for source, neighbors in self._adjacency.items():
            for target, distance_m in neighbors:
                key = tuple(sorted((source, target)))
                if key in seen:
                    continue
                seen.add(key)
                emitted_edges.append(
                    {
                        "source": source,
                        "target": target,
                        "distance_m": distance_m,
                    }
                )

        return {
            "zones": self.zones,
            "edges": emitted_edges,
        }
