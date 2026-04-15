# Graph Maker

`graphmaker.html` is a browser-based interactive tool for generating, viewing, and analyzing a wide range of finite graphs. It was designed to support classroom exploration of graph theory topics such as Euler paths, Hamilton paths, and planarity, while remaining simple to run on common desktop and mobile devices.

Because the tool is contained in a single HTML file, it can be used locally in a browser or hosted through GitHub Pages for easy student access.

## Main components

This repo currently has two closely related pieces:

- `graphmaker.html` — the main student-facing browser tool
- `codec.py` — a companion Python utility for encoding, decoding, generating, and analyzing Graph Maker graph codes

The HTML tool is the primary code in the repo. The Python codec is best viewed as a supporting utility for instructors, testing, validation, and generating canonical graph-code examples.

## What the tool does

Graph Maker allows the user to create or generate graphs from several families and then study them in both visual and tabular form. Depending on the graph type, the tool supports random generation, graph tracing, and structural analysis.

### Supported outputs

- Visual graph display
- Tabular edge display
- Euler count
- Euler trace by clicking in the table
- Hamilton count
- Hamilton trace by clicking in the table
- Planarity check

### Supported graph families and options

The tool supports the following graph families:

- Regular graphs
- Bipartite graphs
- Rectangular grid graphs
- Cylindrical grid graphs

Depending on the selected family, the tool may also support:

- Seeded random generation
- Directed edges
- Self-loops
- Repeated edges
- Complete graphs
- Vertex-group controls
- Valence statistics controls

## Input compatibility matrix

| Mode | Seed | Regular Graph | Bipartite Graph | Rectangular Grid Graph | Cylindrical Grid Graph | Total Vertices | Grouped Vertices | Valence Statistics | Self Loops | Repeated Edges | Directivity | Completeness |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Regular random simple | ✓ | ✓ |  |  |  | ✓ |  | ✓ |  |  |  |  |
| Regular random + self-loops | ✓ | ✓ |  |  |  | ✓ |  | ✓ | ✓ |  |  |  |
| Regular random + repeated edges | ✓ | ✓ |  |  |  | ✓ |  | ✓ |  | ✓ |  |  |
| Regular random + directed | ✓ | ✓ |  |  |  | ✓ |  | ✓ |  |  | ✓ |  |
| Regular random + self-loops + repeated edges | ✓ | ✓ |  |  |  | ✓ |  | ✓ | ✓ | ✓ |  |  |
| Regular random + self-loops + directed | ✓ | ✓ |  |  |  | ✓ |  | ✓ | ✓ |  | ✓ |  |
| Regular random + repeated edges + directed | ✓ | ✓ |  |  |  | ✓ |  | ✓ |  | ✓ | ✓ |  |
| Regular random + self-loops + repeated edges + directed | ✓ | ✓ |  |  |  | ✓ |  | ✓ | ✓ | ✓ | ✓ |  |
| Regular complete (undirected) |  | ✓ |  |  |  | ✓ |  |  |  |  |  | ✓ |
| Regular complete (directed) |  | ✓ |  |  |  | ✓ |  |  |  |  | ✓ | ✓ |
| Bipartite random simple | ✓ |  | ✓ |  |  |  | ✓ | ✓ |  |  |  |  |
| Bipartite random + repeated edges | ✓ |  | ✓ |  |  |  | ✓ | ✓ |  | ✓ |  |  |
| Bipartite random + directed | ✓ |  | ✓ |  |  |  | ✓ | ✓ |  |  | ✓ |  |
| Bipartite random + repeated edges + directed | ✓ |  | ✓ |  |  |  | ✓ | ✓ |  | ✓ | ✓ |  |
| Bipartite complete (undirected) |  |  | ✓ |  |  |  | ✓ |  |  |  |  | ✓ |
| Bipartite complete (directed) |  |  | ✓ |  |  |  | ✓ |  |  |  | ✓ | ✓ |
| Rectangular grid |  |  |  | ✓ |  |  | ✓ |  |  |  |  |  |
| Cylindrical grid |  |  |  |  | ✓ |  | ✓ |  |  |  |  |  |

## Graph code format

Graph Maker also supports a **structural graph code** format that gives a canonical text representation of a graph. This code is designed to describe the graph itself, not the current screen state. It does **not** encode vertex dragging, zoom/pan state, or display toggles, which keeps the code stable while a user explores the same graph on screen.

A graph code has the form:

```text
<flags>.<a>.<b>.<edges>
```

Example:

```text
00000.4.0.A-B,B-C,C-D
```

This format uses:

- a 5-character `flags` field for graph family and option settings
- size fields `a` and `b` in lowercase base-36
- a canonical edge list using vertex labels like `A`, `B`, `Z`, `AA`, `AB`, ... fileciteturn1file0

### Flags field

The `flags` field is unpacked as:

```text
{graphType}{selfLoops}{allowRepeatedEdges}{directed}{complete}
```

Where:

- `graphType`: `0 = regular`, `1 = bipartite`, `2 = rectangular grid`, `3 = cylindrical grid`
- `selfLoops`: `0 = false`, `1 = true`
- `allowRepeatedEdges`: `0 = false`, `1 = true`
- `directed`: `0 = false`, `1 = true`
- `complete`: `0 = false`, `1 = true` fileciteturn1file0

### Edge tokens

- Undirected edges use `U-V`
- Directed edges use `U>V`
- Repeated identical edges can be compressed with `*count`
- The special token `_` represents an empty edge list, which is only valid for the one-vertex graph. fileciteturn1file0

### Canonicality

The codec sorts edge tokens lexicographically, applies run-length compression, and then requires that decoding followed by re-encoding reproduce the exact same input string. In other words, every accepted graph code is canonical, and two different accepted graph codes cannot describe the same graph.

## About `codec.py`

The companion Python program `codec.py` implements the graph-code system used by Graph Maker. It includes:

- encoding a graph description into canonical graph code
- decoding a graph code back into a validated structural description
- JSON-style inspection output
- graph-family-specific validation rules
- sample generation across graph families
- Euler-path and Hamilton-path counting utilities
- a small Tkinter GUI with **Decode** and **Encode** tabs. fileciteturn1file1

From the code, the GUI supports two main workflows:

- **Decode**: enter a graph code and inspect the analyzed result
- **Encode**: generate sample graphs by family, filtered by Euler/Hamilton existence and planarity, with seed-based generation controls. fileciteturn1file1

The codec also uses `networkx` for graph construction, connectivity checks, and planarity analysis. fileciteturn1file1

## How to use

### Run `graphmaker.html` locally

1. Download or clone this repository.
2. Open `graphmaker.html` in a modern web browser.
3. Choose a graph family and available options.
4. Generate or inspect the graph.
5. Use the visual display and edge table to explore Euler and Hamilton behavior.

### Run `codec.py` locally

1. Make sure Python 3 is installed.
2. Install the required dependency:

```bash
pip install networkx
```

3. Run the codec utility:

```bash
python codec.py
```

4. Use the **Decode** tab to inspect graph codes or the **Encode** tab to generate canonical graph-code examples.

### Host on GitHub Pages

Because the main project is a static HTML tool, it can be published directly with GitHub Pages.

1. Push the repository to GitHub.
2. In the repository settings, enable **GitHub Pages**.
3. Choose the branch and folder that contain `graphmaker.html`.
4. Visit the published site URL in a browser.

## Classroom use

This tool is especially well suited for:

- exploring how graph structure changes when self-loops, repeated edges, or direction are allowed
- comparing regular, bipartite, and grid-based graph families
- investigating Euler and Hamilton questions through both counting and tracing
- checking planarity while simultaneously viewing the graph and its edge table
- giving students a mobile-friendly way to interact with graph theory examples outside class
- preparing stable graph-code examples that can be shared, regenerated, decoded, and checked with the companion codec

## Notes

- Available controls depend on the graph family selected.
- Complete graphs are available only where they are mathematically appropriate in the interface.
- Rectangular and cylindrical grids use grouped-vertex style inputs rather than total-vertex inputs.
- Some analysis features may become expensive on larger graphs, especially for Hamilton counts.
- The graph code is **structural only** and is intended to remain stable across visual exploration of the same graph.

## File overview

- `graphmaker.html` — the main interactive browser tool
- `codec.py` — companion Python graph-code encoder/decoder and analysis utility
- `README.md` — repository overview and usage guide
- `LICENSE` — MIT license text

## License

Copyright (c) 2026 Alan Miller.

This project is released under the **MIT License**.

See the [`LICENSE`](LICENSE) file for the full license text.
