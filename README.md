# Structly — 2D Structural Analysis & FEA Studio

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PyQt6-brightgreen.svg)](https://riverbankcomputing.com/software/pyqt/)
[![FEA Engine](https://img.shields.io/badge/FEA-PyNiteFEA-orange.svg)](https://github.com/JWock82/PyNite)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Structly** is an intuitive, modern 2D structural analysis desktop application built in Python using **PyQt6**, **PyNiteFEA**, and **Matplotlib**. It combines an interactive CAD-like drawing canvas with a finite element solver to model, analyze, and visualize 2D frames, trusses, and beams.

---

## ✨ Features

- **Interactive Canvas & CAD Tools**:
  - Place nodes and draw members with snap-to-grid accuracy.
  - Pan, smooth zoom, and fit-to-view controls.
  - Dynamic cursor coordinates in real-world meters.
- **Boundary Conditions & Hinges**:
  - **Support Types**: Fixed, Pinned, Roller X (horizontal slider), Roller Y (vertical slider), and Free.
  - **Member End Releases**: Axial ($F_x$), Shear ($F_y$), and Moment ($M_z$) releases (internal hinges).
- **Comprehensive Loading**:
  - **Nodal Loads**: Horizontal force ($F_x$), vertical force ($F_y$), and moment ($M_z$).
  - **Member Point Loads**: Arbitrary transverse or axial point loads at specific positions along members.
  - **Distributed Loads**: Uniform and trapezoidal distributed loads along members.
  - **Loads Manager**: Centralized table to inspect, edit, and delete all loads in the model.
- **Structural Analysis & Diagrams**:
  - **$M$ — Bending Moment Diagram (BMD)**: With peak values and curvature shading.
  - **$T$ — Shear Force Diagram (SFD)**.
  - **$N$ — Axial Force Diagram (AFD)**.
  - **$R$ — Support Reactions**: Visual reaction vectors overlaid on supports + detailed bar charts.
  - **Displacements**: Joint displacements ($\Delta_x, \Delta_y$) and rotation ($\theta_z$).
- **Influence Line Diagrams (ILD)**:
  - High-fidelity moving load sweep ($1\,000+$ sampling points) to compute exact influence lines for bending moments, shear forces, or axial forces along designated load paths.
- **Modern UI & Theming**:
  - Dark Mode and Light Mode toggles.
  - Built-in engineering examples:
    - Simply-Supported Beam with UDL
    - Propped Cantilever with Point Load
    - Portal Frame with Lateral Load
- **Project Serialization**: Save and load structural models to standard `.str` / JSON files.

---

## 🛠️ Architecture

```
structly/
├── engine/             # FEA integration layer
│   └── solver.py       # Bridge to PyNiteFEA, analysis runner & ILD engine
├── models/             # Pure data model (reactive with PyQt signals)
│   ├── node.py         # Nodes, supports, nodal loads
│   ├── member.py       # Members, end releases, distributed & point loads
│   ├── section.py      # Cross-section geometry & material properties (E, G, A, I)
│   └── project.py      # Project container, JSON serialization, validation
├── ui/                 # Graphical user interface (PyQt6)
│   ├── canvas.py       # QGraphicsScene & QGraphicsView interactive workspace
│   ├── main_window.py  # Main window, toolbar, properties, Matplotlib panels
│   ├── loads_dialog.py # Dialog to add nodal and member loads
│   ├── loads_manager_dialog.py # Unified table of all loads
│   └── influence_dialog.py     # Configuration dialog for Influence Lines
├── utils/
│   └── coords.py       # World-to-scene coordinate mapping & snap-to-grid
├── main.py             # Application entry point
├── structly.bat        # Windows quick launcher
└── requirements.txt    # Python dependencies
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Git

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/structly.git
   cd structly
   ```

2. **Create and activate a virtual environment:**
   - **Windows:**
     ```cmd
     python -m venv .venv
     .venv\Scripts\activate
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Running Structly

- **On Windows (one-click launcher):**
  ```cmd
  structly.bat
  ```
- **Or via Python:**
  ```bash
  python main.py
  ```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|:---:|---|
| <kbd>S</kbd> | Select / Move Tool |
| <kbd>N</kbd> | Place Node Tool |
| <kbd>M</kbd> | Draw Member Tool |
| <kbd>Del</kbd> | Delete Selected Item |
| <kbd>L</kbd> | Open Loads Manager |
| <kbd>F5</kbd> | Run Analysis |
| <kbd>Ctrl</kbd> + <kbd>R</kbd> | Toggle Support Reactions Overlay |
| <kbd>I</kbd> | Influence Line Diagram Tool |
| <kbd>F</kbd> | Fit View to Canvas |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
