#!/usr/bin/env python3

import json
import queue
import random
import re
import threading
import traceback
import tkinter as tk
from collections import Counter, defaultdict, deque
from tkinter import messagebox, ttk
from typing import Any, Dict, Iterable, List, Optional, Tuple

import networkx as nx

"""Encode/decode Graph Maker structural graph codes.

Format:
  <flags>.<a>.<b>.<edges>

Flags are unpacked as 5 digits:
  {graphType}{selfLoops}{allowRepeatedEdges}{directed}{complete}

Examples:
  00000.4.0.A-B,B-C,C-D
  10001.2.3.A-D,A-E,A-F,B-D,B-E,B-F
"""



def index_to_excel_label(index: int) -> str:
  if index < 0:
    raise ValueError("Index must be nonnegative.")
  label = ""
  n = index + 1
  while n > 0:
    n, rem = divmod(n - 1, 26)
    label = chr(65 + rem) + label
  return label


def excel_label_to_index(label: str) -> int:
  if not isinstance(label, str):
    raise ValueError("Invalid vertex label.")
  label = label.strip().upper()
  if not label or any(ch < 'A' or ch > 'Z' for ch in label):
    raise ValueError("Invalid vertex label.")
  value = 0
  for ch in label:
    value = value * 26 + (ord(ch) - 64)
  return value - 1


def generate_vertex_labels(n: int) -> List[str]:
  return [index_to_excel_label(i) for i in range(n)]


class GraphCodeCodec:
  @staticmethod
  def flags_string(desc: Dict[str, Any]) -> str:
    gt = int(desc["graphType"])
    if gt not in (0, 1, 2, 3):
      raise ValueError("Invalid graphType.")
    return f"{gt}{1 if desc.get('selfLoops') else 0}{1 if desc.get('allowRepeatedEdges') else 0}{1 if desc.get('directed') else 0}{1 if desc.get('complete') else 0}"

  @staticmethod
  def parse_flags(s: str) -> Dict[str, Any]:
    s = str(s).strip()
    if not re.fullmatch(r"[0-3][01][01][01][01]", s):
      raise ValueError("Invalid flags field.")
    return {
      "graphType": int(s[0]),
      "selfLoops": s[1] == "1",
      "allowRepeatedEdges": s[2] == "1",
      "directed": s[3] == "1",
      "complete": s[4] == "1",
    }

  @staticmethod
  def base36(n: int) -> str:
    if not isinstance(n, int) or n < 0:
      raise ValueError("Invalid nonnegative integer.")
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
      return "0"
    out = ""
    while n:
      n, rem = divmod(n, 36)
      out = chars[rem] + out
    return out

  @staticmethod
  def parse36(s: str) -> int:
    s = str(s).strip().lower()
    if not re.fullmatch(r"[0-9a-z]+", s):
      raise ValueError("Invalid base36 token.")
    return int(s, 36)

  @staticmethod
  def labels_for_description(desc: Dict[str, Any]) -> List[str]:
    gt = int(desc["graphType"])
    if gt == 0:
      return generate_vertex_labels(int(desc["basicN"]))
    if gt == 1:
      return generate_vertex_labels(int(desc["specialM"]) + int(desc["specialP"]))
    return generate_vertex_labels(int(desc["specialM"]) * int(desc["specialP"]))

  @classmethod
  def canonical_edge_records(cls, desc: Dict[str, Any]) -> List[str]:
    labels = cls.labels_for_description(desc)
    records: List[str] = []
    directed = bool(desc.get("directed"))
    for edge in desc.get("edges", []):
      if directed:
        src, dst = edge.get("orientation", [edge["u"], edge["v"]])
        records.append(f"{labels[src]}>{labels[dst]}")
      else:
        a = min(edge["u"], edge["v"])
        b = max(edge["u"], edge["v"])
        records.append(f"{labels[a]}-{labels[b]}")
    records.sort()
    return records

  @classmethod
  def validate_description(cls, desc: Dict[str, Any]) -> None:
    labels = cls.labels_for_description(desc)
    n = len(labels)
    gt = int(desc["graphType"])
    if gt not in (0, 1, 2, 3):
      raise ValueError("Invalid graphType.")
    if gt == 0 and int(desc.get("basicN", 0)) < 1:
      raise ValueError("Invalid basicN.")
    if gt != 0 and (int(desc.get("specialM", 0)) < 1 or int(desc.get("specialP", 0)) < 1):
      raise ValueError("Invalid special graph dimensions.")

    directed = bool(desc.get("directed"))
    allow_repeated = bool(desc.get("allowRepeatedEdges"))
    self_loops = bool(desc.get("selfLoops"))
    complete = bool(desc.get("complete"))
    undirected_counts: Counter[str] = Counter()
    directed_counts: Counter[str] = Counter()

    for edge in desc.get("edges", []):
      u, v = edge["u"], edge["v"]
      if not isinstance(u, int) or not isinstance(v, int) or u < 0 or v < 0 or u >= n or v >= n:
        raise ValueError("Edge vertex index out of range.")
      if not self_loops and u == v:
        raise ValueError("Self-loop not allowed by graph code flags.")
      if directed:
        orient = edge.get("orientation")
        if not isinstance(orient, list) or len(orient) != 2:
          raise ValueError("Directed edge missing orientation.")
        if orient[0] != u or orient[1] != v:
          raise ValueError("Directed edge orientation mismatch.")
        directed_counts[f"{u}>{v}"] += 1
      a, b = min(u, v), max(u, v)
      undirected_counts[f"{a}-{b}"] += 1

    if not allow_repeated:
      seen = set()
      for edge in desc.get("edges", []):
        key = f"{edge['u']}>{edge['v']}" if directed else f"{min(edge['u'], edge['v'])}-{max(edge['u'], edge['v'])}"
        if key in seen:
          raise ValueError("Repeated edges not allowed by graph code flags.")
        seen.add(key)

    if gt == 1:
      if self_loops:
        raise ValueError("Bipartite graphs cannot allow self-loops.")
      left_size = int(desc["specialM"])
      for edge in desc.get("edges", []):
        left_u = edge["u"] < left_size
        left_v = edge["v"] < left_size
        if left_u == left_v:
          raise ValueError("Bipartite edges must connect the two different parts.")

    if gt in (2, 3):
      if self_loops:
        raise ValueError("Grid-family graphs cannot allow self-loops.")
      if allow_repeated:
        raise ValueError("Grid-family graphs cannot allow repeated edges.")
      if directed:
        raise ValueError("Grid-family graphs cannot be directed.")
      if complete:
        raise ValueError("Grid-family graphs cannot be complete.")
      m = int(desc["specialM"])
      p = int(desc["specialP"])
      expected = set()
      idx = lambda x, y: y * m + x
      if gt == 2:
        for y in range(p):
          for x in range(m):
            if x + 1 < m:
              expected.add(f"{idx(x, y)}-{idx(x + 1, y)}")
            if y + 1 < p:
              expected.add(f"{idx(x, y)}-{idx(x, y + 1)}")
      else:
        for r in range(m):
          for a in range(p):
            cur = r * p + a
            around = r * p + ((a + 1) % p)
            expected.add(f"{min(cur, around)}-{max(cur, around)}")
            if r + 1 < m:
              out = (r + 1) * p + a
              expected.add(f"{min(cur, out)}-{max(cur, out)}")
      if set(undirected_counts) != expected:
        raise ValueError("Grid-family graph edges must match the required grid adjacency exactly.")
      if any(undirected_counts[k] != 1 for k in expected):
        raise ValueError("Grid-family graph edges must match the required grid adjacency exactly.")

    if complete:
      if self_loops:
        raise ValueError("Complete graphs cannot allow self-loops.")
      if allow_repeated:
        raise ValueError("Complete graphs cannot allow repeated edges.")
      expected_undir: Counter[str] = Counter()
      expected_dir: Counter[str] = Counter()
      if gt == 0:
        for i in range(n):
          for j in range(i + 1, n):
            expected_undir[f"{i}-{j}"] = 1
            if directed:
              expected_dir[f"{i}>{j}"] = 1
              expected_dir[f"{j}>{i}"] = 1
      elif gt == 1:
        left_size = int(desc["specialM"])
        for i in range(left_size):
          for j in range(left_size, n):
            expected_undir[f"{i}-{j}"] = 1
            if directed:
              expected_dir[f"{i}>{j}"] = 1
              expected_dir[f"{j}>{i}"] = 1
      if directed:
        if directed_counts != expected_dir:
          raise ValueError("Complete graph edges must match the required complete adjacency exactly.")
      else:
        if undirected_counts != expected_undir:
          raise ValueError("Complete graph edges must match the required complete adjacency exactly.")

    if n > 1:
      if not desc.get("edges"):
        raise ValueError("Graph code must describe a connected graph.")
      adj = defaultdict(list)
      for edge in desc.get("edges", []):
        u, v = edge["u"], edge["v"]
        adj[u].append(v)
        if u != v:
          adj[v].append(u)
      seen = {0}
      q = deque([0])
      while q:
        cur = q.popleft()
        for nxt in adj[cur]:
          if nxt not in seen:
            seen.add(nxt)
            q.append(nxt)
      if len(seen) != n:
        raise ValueError("Graph code must describe a connected graph.")

  @classmethod
  def encode_description(cls, desc: Dict[str, Any]) -> str:
    cls.validate_description(desc)
    gt = int(desc["graphType"])
    a = int(desc["basicN"] if gt == 0 else desc["specialM"])
    b = 0 if gt == 0 else int(desc["specialP"])
    flags = cls.flags_string(desc)
    records = cls.canonical_edge_records(desc)
    parts = []
    i = 0
    while i < len(records):
      j = i + 1
      while j < len(records) and records[j] == records[i]:
        j += 1
      count = j - i
      parts.append(f"{records[i]}*{cls.base36(count)}" if count > 1 else records[i])
      i = j
    edges = ",".join(parts) if parts else "_"
    return f"{flags}.{cls.base36(a)}.{cls.base36(b)}.{edges}"

  @classmethod
  def decode_code(cls, code: str) -> Dict[str, Any]:
    pieces = str(code).strip().split('.')
    if len(pieces) != 4:
      raise ValueError("Invalid graph code format.")
    header = cls.parse_flags(pieces[0])
    a = cls.parse36(pieces[1])
    b = cls.parse36(pieces[2])
    desc: Dict[str, Any] = {
      "version": 1,
      "graphType": header["graphType"],
      "basicN": a if header["graphType"] == 0 else 0,
      "specialM": 0 if header["graphType"] == 0 else a,
      "specialP": 0 if header["graphType"] == 0 else b,
      "selfLoops": header["selfLoops"],
      "allowRepeatedEdges": header["allowRepeatedEdges"],
      "directed": header["directed"],
      "complete": header["complete"],
      "edges": [],
    }
    labels = cls.labels_for_description(desc)
    n = len(labels)
    edge_part = pieces[3]
    if edge_part != '_':
      for token in [t for t in edge_part.split(',') if t]:
        edge_token, *count_part = token.split('*')
        count = cls.parse36(count_part[0]) if count_part else 1
        if count < 1:
          raise ValueError("Invalid repeated-edge count.")
        if desc["directed"]:
          m = re.fullmatch(r"([A-Z]+)>([A-Z]+)", edge_token, flags=re.I)
          if not m:
            raise ValueError("Invalid directed edge token.")
          src = excel_label_to_index(m.group(1))
          dst = excel_label_to_index(m.group(2))
          if src >= n or dst >= n:
            raise ValueError("Edge vertex label out of range.")
          for _ in range(count):
            desc["edges"].append({"u": src, "v": dst, "orientation": [src, dst]})
        else:
          m = re.fullmatch(r"([A-Z]+)-([A-Z]+)", edge_token, flags=re.I)
          if not m:
            raise ValueError("Invalid undirected edge token.")
          u = excel_label_to_index(m.group(1))
          v = excel_label_to_index(m.group(2))
          if u >= n or v >= n:
            raise ValueError("Edge vertex label out of range.")
          if u > v:
            raise ValueError("Undirected edges must be canonical.")
          for _ in range(count):
            desc["edges"].append({"u": u, "v": v})
    cls.validate_description(desc)
    canonical = cls.encode_description(desc)
    if canonical != str(code).strip():
      raise ValueError("Non-canonical graph code.")
    return desc

  @classmethod
  def description_to_json(cls, desc: Dict[str, Any]) -> Dict[str, Any]:
    labels = cls.labels_for_description(desc)
    return {
      "version": 1,
      "graphType": desc["graphType"],
      "basicN": desc["basicN"],
      "specialM": desc["specialM"],
      "specialP": desc["specialP"],
      "selfLoops": bool(desc.get("selfLoops")),
      "allowRepeatedEdges": bool(desc.get("allowRepeatedEdges")),
      "directed": bool(desc.get("directed")),
      "complete": bool(desc.get("complete")),
      "labels": labels,
      "edges": [
        {
          "u": edge["u"],
          "v": edge["v"],
          "uLabel": labels[edge["u"]],
          "vLabel": labels[edge["v"]],
          **({"orientation": edge["orientation"]} if desc.get("directed") else {}),
        }
        for edge in desc.get("edges", [])
      ],
    }


MAX_COUNT = 1000
GRAPH_TYPE_NAMES = {
  0: "regular",
  1: "bipartite",
  2: "rectangular grid",
  3: "cylindrical grid",
}


def make_nx_graph(desc: Dict[str, Any]) -> nx.Graph | nx.MultiGraph | nx.DiGraph | nx.MultiDiGraph:
  labels = GraphCodeCodec.labels_for_description(desc)
  directed = bool(desc.get("directed"))
  multigraph = bool(desc.get("allowRepeatedEdges")) or (bool(desc.get("complete")) and directed)
  if directed:
    g = nx.MultiDiGraph() if multigraph else nx.DiGraph()
  else:
    g = nx.MultiGraph() if multigraph else nx.Graph()
  g.add_nodes_from(labels)
  for edge in desc.get("edges", []):
    if directed:
      src, dst = edge.get("orientation", [edge["u"], edge["v"]])
      g.add_edge(labels[src], labels[dst])
    else:
      g.add_edge(labels[edge["u"]], labels[edge["v"]])
  return g


def _underlying_connected(g: nx.Graph | nx.DiGraph | nx.MultiGraph | nx.MultiDiGraph) -> bool:
  if g.number_of_nodes() <= 1:
    return True
  if g.is_directed():
    h = nx.Graph()
    h.add_nodes_from(g.nodes)
    h.add_edges_from((u, v) for u, v in g.edges())
    active = [node for node in h.nodes if h.degree(node) > 0]
    if len(active) <= 1:
      return True
    return nx.is_connected(h.subgraph(active))
  active = [node for node in g.nodes if g.degree(node) > 0]
  if len(active) <= 1:
    return True
  return nx.is_connected(g.subgraph(active))


def count_euler_paths(graph, start=None, end=None, limit: int = MAX_COUNT):
  if graph.number_of_edges() == 0:
    return 1 if (start is None or end is None or start == end) else 0
  if not _underlying_connected(graph):
    return 0

  if graph.is_directed():
    outdeg = dict(graph.out_degree())
    indeg = dict(graph.in_degree())
    plus = [n for n in graph.nodes if outdeg[n] - indeg[n] == 1]
    minus = [n for n in graph.nodes if indeg[n] - outdeg[n] == 1]
    bad = [n for n in graph.nodes if abs(outdeg[n] - indeg[n]) > 1]
    if bad:
      return 0
    if plus or minus:
      if len(plus) != 1 or len(minus) != 1:
        return 0
      if start is not None and start != plus[0]:
        return 0
      if end is not None and end != minus[0]:
        return 0
      starts = [plus[0]]
    else:
      if start is not None and end is not None and start != end:
        return 0
      starts = [start] if start is not None else [n for n in graph.nodes if graph.out_degree(n) + graph.in_degree(n) > 0]

    adjacency = {n: [] for n in graph.nodes}
    indexed_edges = []
    if isinstance(graph, nx.MultiDiGraph):
      for u, v, k in graph.edges(keys=True):
        tok = (u, v, int(k))
        indexed_edges.append(tok)
        adjacency[u].append(tok)
    else:
      edge_counter = 0
      for u, v in graph.edges():
        tok = (u, v, edge_counter)
        edge_counter += 1
        indexed_edges.append(tok)
        adjacency[u].append(tok)

    used = set()
    count = 0

    def dfs(node, used_count):
      nonlocal count
      if count > limit:
        return
      if used_count == len(indexed_edges):
        if end is None or node == end:
          count += 1
        return
      for edge in adjacency[node]:
        if edge in used:
          continue
        used.add(edge)
        dfs(edge[1], used_count + 1)
        used.remove(edge)

    for s in starts:
      dfs(s, 0)
      if count > limit:
        break
    return ">1000" if count > limit else count

  odd = [n for n in graph.nodes if graph.degree(n) % 2 == 1]
  if len(odd) not in (0, 2):
    return 0
  if len(odd) == 2:
    if start is not None and start not in odd:
      return 0
    if end is not None and end not in odd:
      return 0
    if start is not None and end is not None and start == end:
      return 0
    starts = [start] if start is not None else odd
  else:
    if start is not None and end is not None and start != end:
      return 0
    starts = [start] if start is not None else [n for n in graph.nodes if graph.degree(n) > 0]

  adjacency = {n: [] for n in graph.nodes}
  indexed_edges = []
  if isinstance(graph, nx.MultiGraph):
    for u, v, k in graph.edges(keys=True):
      tok = (u, v, int(k))
      indexed_edges.append(tok)
      adjacency[u].append(tok)
      adjacency[v].append(tok)
  else:
    edge_counter = 0
    for u, v in graph.edges():
      tok = (u, v, edge_counter)
      edge_counter += 1
      indexed_edges.append(tok)
      adjacency[u].append(tok)
      adjacency[v].append(tok)

  used = set()
  count = 0

  def other(edge, node):
    return edge[1] if edge[0] == node else edge[0]

  def dfs(node, used_count):
    nonlocal count
    if count > limit:
      return
    if used_count == len(indexed_edges):
      if end is None or node == end:
        count += 1
      return
    for edge in adjacency[node]:
      if edge in used:
        continue
      used.add(edge)
      dfs(other(edge, node), used_count + 1)
      used.remove(edge)

  for s in starts:
    dfs(s, 0)
    if count > limit:
      break
  return ">1000" if count > limit else count


def count_hamilton_paths(graph, start=None, end=None, limit: int = MAX_COUNT):
  nodes = list(graph.nodes)
  if not nodes:
    return 0
  if start is not None and start not in graph:
    return 0
  if end is not None and end not in graph:
    return 0
  node_index = {node: i for i, node in enumerate(nodes)}
  all_mask = (1 << len(nodes)) - 1
  directed = graph.is_directed()
  adjacency = {node: {} for node in nodes}

  if directed:
    for u, v in graph.edges():
      if u == v:
        continue
      adjacency[u][v] = adjacency[u].get(v, 0) + 1
  else:
    for u, v in graph.edges():
      if u == v:
        continue
      adjacency[u][v] = adjacency[u].get(v, 0) + 1
      adjacency[v][u] = adjacency[v].get(u, 0) + 1

  memo = {}
  count_circuit = start is not None and end is not None and start == end

  def dfs(current, mask, start_node):
    key = (current, mask, start_node)
    if key in memo:
      return memo[key]
    if mask == all_mask:
      if count_circuit:
        ans = adjacency[current].get(start_node, 0)
      else:
        ans = 1 if end is None or current == end else 0
      memo[key] = ans
      return ans
    total = 0
    for nxt, mult in adjacency[current].items():
      bit = 1 << node_index[nxt]
      if mask & bit:
        continue
      subtotal = dfs(nxt, mask | bit, start_node)
      if subtotal:
        total += mult * subtotal
        if total > limit:
          memo[key] = limit + 1
          return limit + 1
    memo[key] = total
    return total

  starts = [start] if start is not None else nodes
  total = 0
  for s in starts:
    total += dfs(s, 1 << node_index[s], s)
    if total > limit:
      return ">1000"
  return total


def analyze_description(desc: Dict[str, Any], limit: int = MAX_COUNT) -> Dict[str, Any]:
  graph = make_nx_graph(desc)
  planar = nx.check_planarity(nx.Graph(graph), counterexample=False)[0]
  nodes = list(graph.nodes)

  euler_path = {"exists": False, "start": None, "end": None, "count": 0}
  euler_circuit = {"exists": False, "start": None, "end": None, "count": 0}
  hamilton_path = {"exists": False, "start": None, "end": None, "count": 0}
  hamilton_circuit = {"exists": False, "start": None, "end": None, "count": 0}

  # Euler circuit
  for node in nodes:
    c = count_euler_paths(graph, node, node, limit=1)
    if c != 0:
      euler_circuit = {"exists": True, "start": node, "end": node, "count": count_euler_paths(graph, node, node, limit=limit)}
      break
  # Euler path
  if euler_circuit["exists"]:
    euler_path = dict(euler_circuit)
  else:
    found = False
    for u in nodes:
      for v in nodes:
        if u == v:
          continue
        c = count_euler_paths(graph, u, v, limit=1)
        if c != 0:
          euler_path = {"exists": True, "start": u, "end": v, "count": count_euler_paths(graph, u, v, limit=limit)}
          found = True
          break
      if found:
        break

  # Hamilton circuit
  for node in nodes:
    c = count_hamilton_paths(graph, node, node, limit=1)
    if c != 0:
      hamilton_circuit = {"exists": True, "start": node, "end": node, "count": count_hamilton_paths(graph, node, node, limit=limit)}
      break
  # Hamilton path
  if hamilton_circuit["exists"]:
    hamilton_path = dict(hamilton_circuit)
  else:
    found = False
    for u in nodes:
      for v in nodes:
        if u == v:
          continue
        c = count_hamilton_paths(graph, u, v, limit=1)
        if c != 0:
          hamilton_path = {"exists": True, "start": u, "end": v, "count": count_hamilton_paths(graph, u, v, limit=limit)}
          found = True
          break
      if found:
        break

  return {
    "code": GraphCodeCodec.encode_description(desc),
    "family": family_label({
      "graphType": int(desc["graphType"]),
      "selfLoops": bool(desc.get("selfLoops")),
      "allowRepeatedEdges": bool(desc.get("allowRepeatedEdges")),
      "directed": bool(desc.get("directed")),
      "complete": bool(desc.get("complete")),
    }),
    "planar": planar,
    "euler_path": euler_path,
    "euler_circuit": euler_circuit,
    "hamilton_path": hamilton_path,
    "hamilton_circuit": hamilton_circuit,
  }


def family_label(spec: Dict[str, Any]) -> str:
  gt = int(spec["graphType"])
  directed = bool(spec.get("directed"))
  complete = bool(spec.get("complete"))
  self_loops = bool(spec.get("selfLoops"))
  repeated = bool(spec.get("allowRepeatedEdges"))

  if gt == 0:
    if complete:
      base = "regular complete"
    elif self_loops and repeated:
      base = "regular with self-loops and repeated edges"
    elif self_loops:
      base = "regular with self-loops"
    elif repeated:
      base = "regular with repeated edges"
    else:
      base = "regular simple"
    suffix = "directed" if directed else "undirected"
    return f"{base}, {suffix}"

  if gt == 1:
    if complete:
      base = "bipartite complete"
    elif repeated:
      base = "bipartite with repeated edges"
    else:
      base = "bipartite simple"
    suffix = "directed" if directed else "undirected"
    return f"{base}, {suffix}"

  if gt == 2:
    return "rectangular grid"
  if gt == 3:
    return "cylindrical grid"
  raise ValueError("Invalid graphType.")

def enumerate_family_specs() -> List[Dict[str, Any]]:
  specs = []
  # regular
  for directed in [False, True]:
    for complete in [False, True]:
      for self_loops in [False, True]:
        for repeated in [False, True]:
          if complete and (self_loops or repeated):
            continue
          specs.append({
            "graphType": 0,
            "directed": directed,
            "complete": complete,
            "selfLoops": self_loops,
            "allowRepeatedEdges": repeated,
          })
  # bipartite
  for directed in [False, True]:
    for complete in [False, True]:
      for repeated in [False, True]:
        if complete and repeated:
          continue
        specs.append({
          "graphType": 1,
          "directed": directed,
          "complete": complete,
          "selfLoops": False,
          "allowRepeatedEdges": repeated,
        })
  # grids
  specs.append({"graphType": 2, "directed": False, "complete": False, "selfLoops": False, "allowRepeatedEdges": False})
  specs.append({"graphType": 3, "directed": False, "complete": False, "selfLoops": False, "allowRepeatedEdges": False})
  out = []
  seen = set()
  for spec in specs:
    label = family_label(spec)
    if label not in seen:
      seen.add(label)
      out.append({**spec, "label": label})
  out.sort(key=lambda s: (s["graphType"], s["label"]))
  return out


FAMILY_SPECS = enumerate_family_specs()


def _ensure_connected_undirected(edge_list: List[Tuple[int, int]], n: int, allow_repeated: bool, rng: random.Random, bipartite_parts: Optional[Tuple[List[int], List[int]]] = None) -> None:
  if n <= 1:
    return
  g = nx.MultiGraph() if allow_repeated else nx.Graph()
  g.add_nodes_from(range(n))
  g.add_edges_from(edge_list)
  comps = list(nx.connected_components(g))
  while len(comps) > 1:
    c1 = list(comps[0])
    c2 = list(comps[1])
    if bipartite_parts is None:
      u = rng.choice(c1)
      v = rng.choice(c2)
    else:
      left, right = bipartite_parts
      left1 = [x for x in c1 if x in left]
      right1 = [x for x in c1 if x in right]
      left2 = [x for x in c2 if x in left]
      right2 = [x for x in c2 if x in right]
      choices = []
      if left1 and right2:
        choices.append((rng.choice(left1), rng.choice(right2)))
      if right1 and left2:
        choices.append((rng.choice(left2), rng.choice(right1)))
      if not choices:
        choices.append((rng.choice(left), rng.choice(right)))
      u, v = rng.choice(choices)
    edge_list.append((u, v))
    g.add_edge(u, v)
    comps = list(nx.connected_components(g))


def _random_valence_params(rng: random.Random) -> Tuple[float, float]:
  mean = round(rng.uniform(1.5, 4.5), 1)
  std = round(rng.uniform(0.4, 2.2), 1)
  return mean, std


def _split_bipartite(total_vertices: int, rng: random.Random) -> Tuple[int, int]:
  if total_vertices < 2:
    total_vertices = 2
  m = rng.randint(1, total_vertices - 1)
  p = total_vertices - m
  return m, p


def _factor_pairs(n: int) -> List[Tuple[int, int]]:
  return [(a, n // a) for a in range(1, n + 1) if n % a == 0]


def _regular_edges(config: Dict[str, Any], rng: random.Random) -> List[Dict[str, Any]]:
  n = int(config["basicN"])
  self_loops = bool(config.get("selfLoops"))
  allow_repeated = bool(config.get("allowRepeatedEdges"))
  directed = bool(config.get("directed"))
  complete = bool(config.get("complete"))
  if complete:
    edges = []
    for i in range(n):
      for j in range(i + 1, n):
        if directed:
          edges.append({"u": i, "v": j, "orientation": [i, j]})
          edges.append({"u": j, "v": i, "orientation": [j, i]})
        else:
          edges.append({"u": i, "v": j})
    return edges

  labels = list(range(n))
  edge_counts = {}
  degrees = {node: 0 for node in labels}
  mean = float(config.get("valenceMean", 3.0))
  std = float(config.get("valenceStd", 2.0))
  targets = {node: max(0, round(rng.gauss(mean, std))) for node in labels}

  def can_add(u: int, v: int) -> bool:
    if not self_loops and u == v:
      return False
    key = (u, v) if directed else tuple(sorted((u, v)))
    if not allow_repeated and edge_counts.get(key, 0) > 0:
      return False
    return True

  for _ in range(3000):
    deficit_nodes = [node for node in labels if degrees[node] < targets[node]]
    if not deficit_nodes:
      break
    u = rng.choice(deficit_nodes)
    v = rng.choice(labels)
    if not can_add(u, v):
      continue
    key = (u, v) if directed else tuple(sorted((u, v)))
    edge_counts[key] = edge_counts.get(key, 0) + 1
    if u == v:
      degrees[u] += 2
    else:
      degrees[u] += 1
      degrees[v] += 1

  undir_edges = []
  for (u, v), count in edge_counts.items():
    undir_edges.extend([(u, v)] * count)
  _ensure_connected_undirected(undir_edges, n, allow_repeated, rng)

  edges = []
  if directed:
    for u, v in undir_edges:
      if u == v:
        edges.append({"u": u, "v": v, "orientation": [u, v]})
      elif rng.random() < 0.5:
        edges.append({"u": u, "v": v, "orientation": [u, v]})
      else:
        edges.append({"u": v, "v": u, "orientation": [v, u]})
  else:
    edges = [{"u": min(u, v), "v": max(u, v)} for u, v in undir_edges]
  return edges


def _bipartite_edges(config: Dict[str, Any], rng: random.Random) -> List[Dict[str, Any]]:
  m = int(config["specialM"])
  p = int(config["specialP"])
  n = m + p
  directed = bool(config.get("directed"))
  allow_repeated = bool(config.get("allowRepeatedEdges"))
  complete = bool(config.get("complete"))
  left = list(range(m))
  right = list(range(m, n))
  if complete:
    edges = []
    for i in left:
      for j in right:
        if directed:
          edges.append({"u": i, "v": j, "orientation": [i, j]})
          edges.append({"u": j, "v": i, "orientation": [j, i]})
        else:
          edges.append({"u": i, "v": j})
    return edges

  pairs = {}
  mean = float(config.get("valenceMean", 3.0))
  std = float(config.get("valenceStd", 2.0))
  for u in left:
    desired = max(1, min(len(right), round(rng.gauss(mean, std))))
    chosen = [rng.choice(right) for _ in range(desired)] if allow_repeated else rng.sample(right, k=desired)
    for v in chosen:
      pairs[(u, v)] = pairs.get((u, v), 0) + 1
  undir_edges = []
  for (u, v), count in pairs.items():
    undir_edges.extend([(u, v)] * count)
  _ensure_connected_undirected(undir_edges, n, allow_repeated, rng, (left, right))

  edges = []
  if directed:
    for u, v in undir_edges:
      if rng.random() < 0.5:
        edges.append({"u": u, "v": v, "orientation": [u, v]})
      else:
        edges.append({"u": v, "v": u, "orientation": [v, u]})
  else:
    edges = [{"u": min(u, v), "v": max(u, v)} for u, v in undir_edges]
  return edges


def _rect_grid_edges(config: Dict[str, Any]) -> List[Dict[str, Any]]:
  m = int(config["specialM"])
  p = int(config["specialP"])
  idx = lambda x, y: y * m + x
  edges = []
  for y in range(p):
    for x in range(m):
      if x + 1 < m:
        edges.append({"u": idx(x, y), "v": idx(x + 1, y)})
      if y + 1 < p:
        edges.append({"u": idx(x, y), "v": idx(x, y + 1)})
  return edges


def _cyl_grid_edges(config: Dict[str, Any]) -> List[Dict[str, Any]]:
  m = int(config["specialM"])
  p = int(config["specialP"])
  edges = []
  for r in range(m):
    for a in range(p):
      cur = r * p + a
      around = r * p + ((a + 1) % p)
      edges.append({"u": min(cur, around), "v": max(cur, around)})
      if r + 1 < m:
        out = (r + 1) * p + a
        edges.append({"u": min(cur, out), "v": max(cur, out)})
  dedup = {(e["u"], e["v"]): e for e in edges}
  return list(dedup.values())


def generate_description(config: Dict[str, Any], seed: Optional[int] = None) -> Dict[str, Any]:
  cfg = json.loads(json.dumps(config))
  gt = int(cfg["graphType"])
  if gt == 1:
    cfg["selfLoops"] = False
  if gt in (2, 3):
    cfg["selfLoops"] = False
    cfg["allowRepeatedEdges"] = False
    cfg["directed"] = False
    cfg["complete"] = False
  if cfg.get("complete"):
    cfg["selfLoops"] = False
    cfg["allowRepeatedEdges"] = False
  rng = random.Random(seed)
  if gt == 0:
    edges = _regular_edges(cfg, rng)
  elif gt == 1:
    edges = _bipartite_edges(cfg, rng)
  elif gt == 2:
    edges = _rect_grid_edges(cfg)
  elif gt == 3:
    edges = _cyl_grid_edges(cfg)
  else:
    raise ValueError("Invalid graphType.")
  desc = {
    "version": 1,
    "graphType": gt,
    "basicN": int(cfg.get("basicN", 0)) if gt == 0 else 0,
    "specialM": int(cfg.get("specialM", 0)) if gt != 0 else 0,
    "specialP": int(cfg.get("specialP", 0)) if gt != 0 else 0,
    "selfLoops": bool(cfg.get("selfLoops")),
    "allowRepeatedEdges": bool(cfg.get("allowRepeatedEdges")),
    "directed": bool(cfg.get("directed")),
    "complete": bool(cfg.get("complete")),
    "edges": edges,
  }
  GraphCodeCodec.validate_description(desc)
  return GraphCodeCodec.decode_code(GraphCodeCodec.encode_description(desc))


def _match_tri(state: str, value: bool) -> bool:
  if state == "either":
    return True
  if state == "yes":
    return value
  if state == "no":
    return not value
  raise ValueError(f"Invalid filter state: {state}")


def matches_filters(info: Dict[str, Any], filters: Dict[str, str]) -> bool:
  return (
    _match_tri(filters["euler_path"], info["euler_path"]["exists"]) and
    _match_tri(filters["euler_circuit"], info["euler_circuit"]["exists"]) and
    _match_tri(filters["hamilton_path"], info["hamilton_path"]["exists"]) and
    _match_tri(filters["hamilton_circuit"], info["hamilton_circuit"]["exists"]) and
    _match_tri(filters["planar"], info["planar"])
  )


def generate_family_samples(selected_labels: Iterable[str], per_family: int, restart_attempts: int, seed: int, total_vertices: int, filters: Dict[str, str]) -> List[Dict[str, Any]]:
  by_label = {spec["label"]: spec for spec in FAMILY_SPECS}
  rng = random.Random(seed)
  results: List[Dict[str, Any]] = []
  for label in selected_labels:
    spec = by_label[label]
    generated = 0
    attempts = 0
    while generated < per_family and attempts < restart_attempts:
      attempts += 1
      trial_seed = rng.randint(0, 2_147_483_647)
      local_rng = random.Random(trial_seed)
      cfg = {
        "graphType": spec["graphType"],
        "selfLoops": spec["selfLoops"],
        "allowRepeatedEdges": spec["allowRepeatedEdges"],
        "directed": spec["directed"],
        "complete": spec["complete"],
      }
      mean, std = _random_valence_params(local_rng)
      cfg["valenceMean"] = mean
      cfg["valenceStd"] = std
      gt = spec["graphType"]
      if gt == 0:
        cfg["basicN"] = max(1, total_vertices)
        cfg["specialM"] = 0
        cfg["specialP"] = 0
      elif gt == 1:
        m, p = _split_bipartite(total_vertices, local_rng)
        cfg["basicN"] = 0
        cfg["specialM"] = m
        cfg["specialP"] = p
      else:
        pairs = _factor_pairs(max(1, total_vertices))
        m, p = local_rng.choice(pairs)
        cfg["basicN"] = 0
        cfg["specialM"] = m
        cfg["specialP"] = p
      try:
        desc = generate_description(cfg, seed=trial_seed)
        info = analyze_description(desc)
      except Exception:
        continue
      if not matches_filters(info, filters):
        continue
      info["seed"] = trial_seed
      info["family"] = label
      results.append(info)
      generated += 1
  return results



TRI_VALUES = ["either", "yes", "no"]


class App(tk.Tk):
  def __init__(self) -> None:
    super().__init__()
    self.title("Graph Codec")
    self.geometry("1320x900")
    self.minsize(1080, 760)

    self._busy = False
    self._worker_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
    self._worker_thread = None
    self._busy_widgets: list[tk.Widget] = []

    self.notebook = ttk.Notebook(self)
    self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

    self.codec_tab = ttk.Frame(self.notebook, padding=10)
    self.gen_tab = ttk.Frame(self.notebook, padding=10)
    self.notebook.add(self.codec_tab, text="Decode")
    self.notebook.add(self.gen_tab, text="Encode")

    self.status_var = tk.StringVar(value="Ready.")
    status_frame = ttk.Frame(self)
    status_frame.pack(fill="x", padx=12, pady=(0, 10))
    ttk.Separator(status_frame, orient="horizontal").pack(fill="x", pady=(0, 6))
    self.status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor="w")
    self.status_label.pack(fill="x")

    self._build_codec_tab()
    self._build_generator_tab()
    self.after(100, self._poll_worker_queue)

  def _register_busy_widgets(self, *widgets: tk.Widget) -> None:
    for widget in widgets:
      if widget is not None and widget not in self._busy_widgets:
        self._busy_widgets.append(widget)

  def _set_status(self, message: str) -> None:
    self.status_var.set(message)
    self.update_idletasks()

  def _set_busy(self, busy: bool, message: str = "") -> None:
    self._busy = busy
    for widget in self._busy_widgets:
      try:
        widget.configure(state="disabled" if busy else "normal")
      except tk.TclError:
        pass
    try:
      self.configure(cursor="watch" if busy else "")
    except Exception:
      pass
    if message:
      self._set_status(message)
    elif not busy:
      self._set_status("Ready.")

  def _run_background(self, work_fn, success_fn, start_message: str, error_title: str = "Error") -> None:
    if self._busy:
      return
    self._set_busy(True, start_message)

    def runner():
      try:
        result = work_fn()
        self._worker_queue.put(("success", (success_fn, result)))
      except Exception:
        self._worker_queue.put(("error", (error_title, traceback.format_exc())))

    self._worker_thread = threading.Thread(target=runner, daemon=True)
    self._worker_thread.start()

  def _poll_worker_queue(self) -> None:
    try:
      while True:
        kind, payload = self._worker_queue.get_nowait()
        if kind == "success":
          callback, result = payload
          self._set_busy(False)
          callback(result)
        elif kind == "error":
          title, tb = payload
          self._set_busy(False)
          self._set_status("Operation failed.")
          messagebox.showerror(title, tb.splitlines()[-1] if tb.strip() else title)
          print(tb)
    except queue.Empty:
      pass
    self.after(100, self._poll_worker_queue)

  def _make_scrolled_text(self, master, *, wrap="word", height=10):
    frame = ttk.Frame(master)
    text = tk.Text(frame, wrap=wrap, height=height)
    vsb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=vsb.set)
    text.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, text

  def _build_codec_tab(self) -> None:
    frame = self.codec_tab
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)

    self.code_var = tk.StringVar()

    top = ttk.Frame(frame, padding=10)
    top.grid(row=0, column=0, sticky="ew")
    top.columnconfigure(1, weight=1)

    ttk.Label(top, text="Graph Code").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
    code_entry = ttk.Entry(top, textvariable=self.code_var)
    code_entry.grid(row=0, column=1, sticky="ew", pady=6)

    buttons = ttk.Frame(top)
    buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    self.decode_btn = ttk.Button(buttons, text="Decode", command=self.decode_code)
    self.decode_btn.pack(side="left")
    self._register_busy_widgets(self.decode_btn)

    analysis_wrap = ttk.Frame(frame, padding=(10, 0, 10, 10))
    analysis_wrap.grid(row=1, column=0, sticky="nsew")
    analysis_wrap.rowconfigure(0, weight=1)
    analysis_wrap.columnconfigure(0, weight=1)
    analysis_frame, self.analysis_text = self._make_scrolled_text(analysis_wrap, wrap="word", height=24)
    analysis_frame.grid(row=0, column=0, sticky="nsew")

  def _build_generator_tab(self) -> None:
    frame = self.gen_tab
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(0, weight=1)

    self.euler_path_var = tk.StringVar(value="either")
    self.euler_circuit_var = tk.StringVar(value="either")
    self.hamilton_path_var = tk.StringVar(value="either")
    self.hamilton_circuit_var = tk.StringVar(value="either")
    self.planar_var = tk.StringVar(value="either")
    self.num_vertices_var = tk.StringVar(value="7")
    self.per_family_var = tk.StringVar(value="1")
    self.restart_attempts_var = tk.StringVar(value="100")
    self.seed_var = tk.StringVar(value="1")
    self.select_all_var = tk.BooleanVar(value=False)

    controls = ttk.Frame(frame, padding=10)
    controls.grid(row=0, column=0, sticky="nsw")
    controls.columnconfigure(1, weight=1)

    output_wrap = ttk.Frame(frame, padding=8)
    output_wrap.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
    output_wrap.rowconfigure(0, weight=1)
    output_wrap.columnconfigure(0, weight=1)
    out_frame, self.output_text = self._make_scrolled_text(output_wrap, wrap="word", height=30)
    out_frame.grid(row=0, column=0, sticky="nsew")

    row = 0
    def add_combo(label, var):
      nonlocal row
      ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 8))
      cb = ttk.Combobox(controls, textvariable=var, values=TRI_VALUES, state="readonly", width=12)
      cb.grid(row=row, column=1, sticky="ew", pady=4)
      row += 1
      return cb

    add_combo("Euler path exist?", self.euler_path_var)
    add_combo("Euler circuit exist?", self.euler_circuit_var)
    add_combo("Hamilton path exist?", self.hamilton_path_var)
    add_combo("Hamilton circuit exist?", self.hamilton_circuit_var)
    add_combo("Planar graph?", self.planar_var)

    def sync_euler(*_args):
      if self.euler_circuit_var.get() == "yes":
        self.euler_path_var.set("yes")

    def sync_hamilton(*_args):
      if self.hamilton_circuit_var.get() == "yes":
        self.hamilton_path_var.set("yes")

    self.euler_circuit_var.trace_add("write", sync_euler)
    self.hamilton_circuit_var.trace_add("write", sync_hamilton)

    ttk.Separator(controls, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=10)
    row += 1

    entries = [
      ("Number of vertices", self.num_vertices_var),
      ("Graphs per selected family", self.per_family_var),
      ("Restart attempts", self.restart_attempts_var),
      ("Seed", self.seed_var),
    ]
    for label, var in entries:
      ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 8))
      ttk.Entry(controls, textvariable=var, width=14).grid(row=row, column=1, sticky="ew", pady=4)
      row += 1

    ttk.Separator(controls, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=10)
    row += 1

    ttk.Label(controls, text="", font=("TkDefaultFont", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1
    ttk.Checkbutton(controls, text="Select all", variable=self.select_all_var, command=self.toggle_all_families).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 6))
    row += 1

    family_frame = ttk.Frame(controls)
    family_frame.grid(row=row, column=0, columnspan=2, sticky="nsew")
    family_frame.rowconfigure(0, weight=1)
    family_frame.columnconfigure(0, weight=1)
    self.family_listbox = tk.Listbox(family_frame, selectmode="extended", exportselection=False, height=18)
    family_scroll = ttk.Scrollbar(family_frame, orient="vertical", command=self.family_listbox.yview)
    self.family_listbox.configure(yscrollcommand=family_scroll.set)
    self.family_listbox.grid(row=0, column=0, sticky="nsew")
    family_scroll.grid(row=0, column=1, sticky="ns")
    for spec in FAMILY_SPECS:
      self.family_listbox.insert("end", spec["label"])
    self.family_listbox.bind("<<ListboxSelect>>", self._on_family_selection_changed)
    row += 1

    ttk.Label(controls, text="Use Shift/Cmd-click (or Ctrl-click) to select multiple families.", foreground="#555555").grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 10))
    row += 1

    self.generate_btn = ttk.Button(controls, text="Generate", command=self.generate_samples)
    self.generate_btn.grid(row=row, column=0, sticky="w")
    self._register_busy_widgets(self.generate_btn)

  def _on_family_selection_changed(self, _event=None) -> None:
    total = self.family_listbox.size()
    selected = len(self.family_listbox.curselection())
    self.select_all_var.set(total > 0 and selected == total)

  def toggle_all_families(self) -> None:
    self.family_listbox.selection_clear(0, "end")
    if self.select_all_var.get():
      self.family_listbox.selection_set(0, "end")
    self._on_family_selection_changed()

  def _selected_family_labels(self) -> list[str]:
    return [self.family_listbox.get(i) for i in self.family_listbox.curselection()]

  def _format_analysis_output(self, info: dict) -> str:
    return json.dumps(info, indent=2)

  def decode_code(self) -> None:
    code = self.code_var.get().strip()

    def work():
      desc = GraphCodeCodec.decode_code(code)
      return analyze_description(desc)

    def done(info):
      self.analysis_text.delete("1.0", "end")
      self.analysis_text.insert("1.0", self._format_analysis_output(info))
      self._set_status("Decode complete.")

    self._run_background(work, done, "Decoding graph code...", "Decode error")

  def generate_samples(self) -> None:
    labels = self._selected_family_labels()
    if not labels:
      messagebox.showerror("Generate error", "Select at least one graph family.")
      return
    filters = {
      "euler_path": self.euler_path_var.get(),
      "euler_circuit": self.euler_circuit_var.get(),
      "hamilton_path": self.hamilton_path_var.get(),
      "hamilton_circuit": self.hamilton_circuit_var.get(),
      "planar": self.planar_var.get(),
    }
    if filters["euler_circuit"] == "yes":
      filters["euler_path"] = "yes"
    if filters["hamilton_circuit"] == "yes":
      filters["hamilton_path"] = "yes"

    per_family = int(self.per_family_var.get())
    restart_attempts = int(self.restart_attempts_var.get())
    seed = int(self.seed_var.get())
    total_vertices = int(self.num_vertices_var.get())

    def work():
      return generate_family_samples(
        selected_labels=labels,
        per_family=per_family,
        restart_attempts=restart_attempts,
        seed=seed,
        total_vertices=total_vertices,
        filters=filters,
      )

    def done(results):
      lines = []
      for item in results:
        lines.append(f"Family: {item['family']}")
        lines.append(f"Seed: {item['seed']}")
        lines.append(f"Code: {item['code']}")
        ep = item['euler_path']
        ec = item['euler_circuit']
        hp = item['hamilton_path']
        hc = item['hamilton_circuit']
        lines.append(f"Euler path: exists={ep['exists']} start={ep['start']} end={ep['end']} count={ep['count']}")
        lines.append(f"Euler circuit: exists={ec['exists']} start={ec['start']} end={ec['end']} count={ec['count']}")
        lines.append(f"Hamilton path: exists={hp['exists']} start={hp['start']} end={hp['end']} count={hp['count']}")
        lines.append(f"Hamilton circuit: exists={hc['exists']} start={hc['start']} end={hc['end']} count={hc['count']}")
        lines.append(f"Planar: {item['planar']}")
        lines.append("")
      if not lines:
        lines = ["No matching graph codes found for the current settings."]
      self.output_text.delete("1.0", "end")
      self.output_text.insert("1.0", "\n".join(lines))
      self._set_status(f"Generation complete: {len(results)} graph(s).")

    total_requested = len(labels) * per_family
    self._run_background(work, done, f"Generating up to {total_requested} graph(s)...", "Generate error")


if __name__ == "__main__":
  App().mainloop()
