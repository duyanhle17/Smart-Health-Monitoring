from __future__ import annotations

import heapq
from math import inf
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .topology import MineTopology


def _path_cost(
    distance_m: float,
    risk_value: float,
    distance_weight: float,
    risk_weight: float,
) -> float:
    return (distance_weight * distance_m) + (risk_weight * risk_value)


def compute_safest_path(
    topology: MineTopology,
    start_zone: str,
    exit_zones: Sequence[str],
    zone_risk: Dict[str, float],
    blocked_zones: Optional[Iterable[str]] = None,
    distance_weight: float = 1.0,
    risk_weight: float = 8.0,
) -> Tuple[List[str], float]:
    """
    Dijkstra with dynamic risk-based edge cost.

    edge_cost = distance_weight * tunnel_distance + risk_weight * risk(target_zone)
    """
    if start_zone not in topology.zones:
        raise ValueError(f"Unknown start zone: {start_zone}")

    exit_set = set(exit_zones)
    if not exit_set:
        raise ValueError("exit_zones cannot be empty")

    blocked: Set[str] = set(blocked_zones or [])
    if start_zone in blocked:
        return [], inf

    dist: Dict[str, float] = {zone: inf for zone in topology.zones}
    prev: Dict[str, str] = {}
    dist[start_zone] = 0.0

    heap: List[Tuple[float, str]] = [(0.0, start_zone)]

    while heap:
        cost, zone = heapq.heappop(heap)
        if cost > dist[zone]:
            continue

        if zone in exit_set:
            break

        for neighbor, distance_m in topology.neighbors(zone):
            if neighbor in blocked:
                continue

            n_risk = float(zone_risk.get(neighbor, 0.0))
            step_cost = _path_cost(distance_m, n_risk, distance_weight, risk_weight)
            cand = cost + step_cost

            if cand < dist[neighbor]:
                dist[neighbor] = cand
                prev[neighbor] = zone
                heapq.heappush(heap, (cand, neighbor))

    best_exit = None
    best_cost = inf
    for zone in exit_set:
        if dist.get(zone, inf) < best_cost:
            best_exit = zone
            best_cost = dist[zone]

    if best_exit is None or best_cost == inf:
        return [], inf

    path = [best_exit]
    while path[-1] != start_zone:
        path.append(prev[path[-1]])
    path.reverse()

    return path, best_cost
