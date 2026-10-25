from dataclasses import dataclass


@dataclass
class CrossSection:
    """Material and geometric properties. SI units: E/G in kN/m², A in m², I in m⁴."""
    name: str = "Default Steel"
    E: float = 200e6    # Young's modulus  (kN/m²)
    G: float = 80e6     # Shear modulus    (kN/m²)
    A: float = 0.00527  # Cross-section area (m²)
    Iz: float = 26.7e-6 # Moment of inertia – strong axis (m⁴)
    J: float = 1e-6     # Torsional constant (m⁴, nominal for 2-D)

    # PyNite uses 'Iy' as the in-plane bending inertia for members in XZ plane;
    # for our 2-D XY-plane model we map Iz → Iy inside the solver.
    @property
    def Iy(self) -> float:
        return self.Iz

    @classmethod
    def default_steel(cls) -> "CrossSection":
        """Approximate 200UB steel section."""
        return cls(name="Steel 200UB", E=200e6, G=80e6,
                   A=0.00527, Iz=26.7e-6, J=1e-6)

    @classmethod
    def default_concrete(cls) -> "CrossSection":
        """Generic 300×500 mm RC beam."""
        return cls(name="Concrete 300×500", E=30e6, G=12.5e6,
                   A=0.15, Iz=3.125e-3, J=1e-5)
