#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
Elmer FEM .sif Generator for Invar Welding - COMPREHENSIVE PERSISTENCE EDITION
================================================================================

OVERVIEW:
This application generates complete, ready-to-run Elmer FEM input files (.sif), 
Fortran User Defined Functions (UDFs), and lookup tables (.dat) for multiphysics 
welding simulations. 

KEY FEATURES:
1. SINGLE MATERIAL CONFIGURATION: 
   - Material 1 (Invar) is uniformly applied to both Solid_1front (Body 1) 
     and Solid_2back (Body 2). This eliminates dissimilar material confusion 
     while maintaining the distinct geometric solid definitions.
   
2. ADVANCED HEAT SOURCE MODELS:
   - Travelling Gaussian
   - Fixed Gaussian
   - Flat-Top (Super-Gaussian)
   - Double Ellipsoidal (Goldak)
   - Pulsed Gaussian (NEW): Integrates temporally pulsed Gaussian heat source 
     with harmonic modulation (first 3 odd harmonics), apparent heat capacity 
     phase change, and geometry-adjusted effective power as per your specifications.

3. ROBUST ARCHITECTURE:
   - Bulletproof multiselects with defensive filtering to prevent StreamlitAPIException.
   - Intelligent @st.cache_data caching to prevent redundant re-computation of parsers.
   - Complete session state persistence: Downloads never break session state; all 
     generated files remain accessible across tab switches and reruns.
   - One-click ZIP bundling for seamless project distribution.

4. EQUATION-BASED ENTHALPY:
   - Optional analytical H(T) model replaces .dat lookup tables for smoother 
     solver convergence during phase change.

AUTHOR: Generated for Advanced Multiphysics Welding Simulations
DATE: 2026
================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import re
import zipfile
import io
import math
import os

# ==============================================================================
# PAGE CONFIGURATION & CUSTOM STYLING
# ==============================================================================
st.set_page_config(
    page_title="Elmer Weld Generator - Invar (Full)",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for enhanced UI/UX readability
st.markdown("""
<style>
    .stCodeBlock { background-color: #f8f9fa; border-radius: 0.5rem; padding: 1rem; }
    .stTextArea textarea { font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85em; }
    .metric-card { background: #f0f2f6; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #007bff; }
    .download-section { background: #e8f4fd; padding: 1.5rem; border-radius: 0.5rem; margin: 1rem 0; border: 1px solid #b6d4fe; }
    .warning-box { background: #fff3cd; border-left: 4px solid #ffc107; padding: 0.75rem 1rem; margin: 0.5rem 0; border-radius: 0.25rem; }
    .success-box { background: #d4edda; border-left: 4px solid #28a745; padding: 0.75rem 1rem; margin: 0.5rem 0; border-radius: 0.25rem; }
    .info-box { background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 0.75rem 1rem; margin: 0.5rem 0; border-radius: 0.25rem; }
    h1, h2, h3 { color: #2c3e50; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0px 0px; }
    .stTabs [aria-selected="true"] { background-color: #ffffff; border-bottom: 2px solid #007bff; }
</style>
""", unsafe_allow_html=True)

st.title("🔥 Elmer FEM Generator for Invar Welding (Single Material)")
st.markdown("""
**Generate complete `.sif` input files + Fortran UDFs + lookup tables for Invar welding simulations.**  
_Mesh file supplied externally with fixed geometry entities. Both `Solid_1front` and `Solid_2back` utilize **Material 1 (Invar)**._
""")

# ==============================================================================
# HELPER FUNCTIONS: UNIQUE KEY GENERATOR & DEFENSIVE MULTISELECT
# ==============================================================================
def uk(section: str, var: str, suffix: str = "") -> str:
    """
    Generate a unique, predictable key for Streamlit widgets.
    Format: section_var_suffix (trailing underscores stripped)
    This prevents Streamlit's "DuplicateWidgetID" errors during reruns.
    """
    return f"{section}_{var}_{suffix}".strip("_")


def safe_multiselect(label: str, options: list, default: list = None, key: str = None, **kwargs):
    """
    Bulletproof multiselect that filters invalid defaults.
    Prevents StreamlitAPIException when default values aren't in the options list 
    (e.g., when geometry names change or are dynamically updated).
    """
    if default is None:
        default = []
    
    # Filter defaults to only include valid options
    valid_defaults = [d for d in default if d in options]
    
    # Warn user if defaults were stripped
    if len(valid_defaults) < len(default):
        invalid = set(default) - set(options)
        st.warning(f"⚠️ Removed invalid defaults for '{label}': {invalid}")
        
    return st.multiselect(label, options, default=valid_defaults, key=key, **kwargs)


# ==============================================================================
# FIXED GEOMETRY ENTITIES DEFINITION
# ==============================================================================
# These represent the fixed, pre-meshed entities from the external mesh file.
SOLID_NAMES = [
    "Solid_1front", 
    "Solid_2back"
]

FACE_NAMES = [
    "Face_1leftfront", "Face_2leftback", "Face_3frontfront", 
    "Face_4bottomfront", "Face_5topfront", "Face_6interfacefront",
    "Face_7bottomback", "Face_8topback", "Face_9backback",
    "Face_10rightfront", "Face_11rightback"
]

# ==============================================================================
# SESSION STATE INITIALIZATION (COMPREHENSIVE PERSISTENCE)
# ==============================================================================
# Initialize ALL session state keys needed for persistence across reruns.
# This ensures that user inputs and generated files are never lost.
if "generated_content" not in st.session_state:
    st.session_state.generated_content = {}
if "generation_timestamp" not in st.session_state:
    st.session_state.generation_timestamp = None
if "table_data_visc_1" not in st.session_state:
    st.session_state.table_data_visc_1 = None
if "table_data_enth_1" not in st.session_state:
    st.session_state.table_data_enth_1 = None
if "use_enthalpy_udf_1" not in st.session_state:
    st.session_state.use_enthalpy_udf_1 = False
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "materials"

# ==============================================================================
# CACHED HELPER FUNCTIONS FOR PERFORMANCE
# ==============================================================================
@st.cache_data(ttl=3600)
def parse_expression_cached(expr: str, temp_var: str = "temp") -> str:
    """
    Cached version of expression parser for Fortran code generation.
    Converts Python-style math expressions to Fortran double-precision syntax.
    """
    # Replace generic temperature variable
    expr_fortran = expr.replace("T", temp_var)
    
    # Ensure floating point numbers have _dp suffix for double precision
    expr_fortran = re.sub(r'(\d+\.\d+)', r'\1_dp', expr_fortran)
    
    # Ensure integers have .0_dp suffix
    expr_fortran = re.sub(r'(?<!\.)(\b\d+\b)(?!\.)', r'\1.0_dp', expr_fortran)
    
    return expr_fortran


@st.cache_data(ttl=3600)
def extract_udf_code_cached(code_block: str) -> str:
    """
    Cached UDF code extractor - removes leading/trailing markdown formatting 
    and empty lines to ensure clean Fortran file output.
    """
    lines = code_block.split('\n')
    while lines and lines[0].strip() == '':
        lines.pop(0)
    while lines and lines[-1].strip() == '':
        lines.pop()
    return '\n'.join(lines)


@st.cache_data(ttl=3600)
def face_names_to_indices_cached(face_list: list) -> str:
    """
    Cached face name to index converter.
    Extracts the numeric ID from face names (e.g., "Face_4bottomfront" -> "4").
    """
    indices = []
    for face in face_list:
        match = re.search(r'Face_(\d+)', face)
        if match:
            indices.append(match.group(1))
    return " ".join(indices) if indices else "1"


@st.cache_data(ttl=3600)
def compute_enthalpy_preview_cached(T: float, alpha: float, beta1: float, beta2: float, 
                                    beta3: float, gamma: float, T0: float, C: float) -> float:
    """
    Cached enthalpy preview calculator for UI display.
    Computes H(T) = (1/α) * [β₁·T + β₂·max(T-T₀,0) + β₃/(1+exp(-γ·(T-T₀))) + C]
    Includes overflow protection for exponential terms.
    """
    linear_term = beta1 * T
    
    max_val = T - T0
    phase_term = beta2 * max_val if max_val > 0.0 else 0.0
    
    exp_arg = -gamma * (T - T0)
    
    # Prevent floating point overflow in exp()
    if exp_arg > 700.0:
        sigmoid_term = 0.0
    elif exp_arg < -700.0:
        sigmoid_term = beta3
    else:
        exp_val = math.exp(exp_arg)
        denom = 1.0 + exp_val
        sigmoid_term = beta3 / denom if denom > 1.0e-300 else beta3
        
    bracket_sum = linear_term + phase_term + sigmoid_term + C
    
    if abs(alpha) < 1.0e-300:
        return 0.0
        
    return bracket_sum / alpha


# ==============================================================================
# SIDEBAR: GLOBAL SETTINGS & OUTPUT CONFIGURATION
# ==============================================================================
st.sidebar.header("⚙️ Global Settings")

project_name = st.sidebar.text_input(
    "Project Name", 
    value="Invar_Weld_Pulsed", 
    key=uk("global", "project"),
    help="Base name for generated files and project identification."
)

author = st.sidebar.text_input(
    "Author", 
    value="Researcher", 
    key=uk("global", "author"),
    help="Your name or identifier for the .sif file header."
)

date_str = datetime.now().strftime("%Y-%m-%d")

st.sidebar.subheader("📁 Output Directories")
sif_filename = st.sidebar.text_input(
    ".sif Filename", 
    value=f"{project_name.lower()}.sif", 
    key=uk("out", "sif")
)

fortran_dir = st.sidebar.text_input(
    "Fortran UDF Directory", 
    value="./udfs/", 
    key=uk("out", "f90dir"),
    help="Relative path where compiled .so/.dll files will be located."
)

table_dir_visc = st.sidebar.text_input(
    "Viscosity Table Dir", 
    value="./viscosity/", 
    key=uk("out", "viscdir")
)

table_dir_enth = st.sidebar.text_input(
    "Enthalpy Table Dir", 
    value="./specific_enthalpy/", 
    key=uk("out", "enthdir")
)

# Sidebar: Quick access to downloads if content exists
if st.session_state.generated_content:
    st.sidebar.success("✅ Files generated and cached!")
    if st.sidebar.button("📥 Go to Downloads Tab", key="sidebar_goto_downloads"):
        st.session_state.active_tab = "generate"
        st.rerun()
else:
    st.sidebar.info("🔄 Configure parameters below and click 'Generate All Files'")

# ==============================================================================
# TABS NAVIGATION WITH STATE TRACKING
# ==============================================================================
tab_materials, tab_heat, tab_tables, tab_physics, tab_generate = st.tabs([
    "🧪 Material 1 (Invar) & UDFs",
    "🔦 Heat Source Models", 
    "📊 Lookup Tables (.dat)",
    "⚙️ Physics & Boundary Conditions",
    "📥 Generate & Download Files"
])

# ==============================================================================
# TAB 1: MATERIAL 1 (INVAR) & FORTRAN UDFs
# ==============================================================================
with tab_materials:
    st.header("🧪 Material 1 Properties & Linked Fortran UDFs")
    st.markdown('<div class="info-box">🔹 <strong>Single Material Configuration:</strong> Material 1 (Invar) is applied to both <code>Solid_1front</code> and <code>Solid_2back</code>. Expressions automatically update the generated Fortran UDFs in real-time.</div>', unsafe_allow_html=True)
    
    st.subheader("Material 1: Invar (Fe-Ni Alloy)")
    mat_1_name = st.text_input("Material Name", value="Invar", key=uk("mat1", "name"))
    mat_1_melting = st.number_input("Melting Point [K]", value=1700.0, step=0.1, key=uk("mat1", "tmelt"), help="Solidus/Liquidus midpoint for phase change modeling.")
    
    st.markdown("**Temperature-Dependent Property Expressions** (T in Kelvin):")
    
    st.markdown("🔹 **Density ρ(T)** [kg/m³]")
    dens_1_s_expr = st.text_input("Solid phase: ρ = ", value="8100.0 - 0.11*(T - 298.0)", key=uk("mat1", "dens_s_expr"))
    dens_1_l_expr = st.text_input("Liquid phase: ρ = ", value="7500.0 - 0.28*(T - 1700.0)", key=uk("mat1", "dens_l_expr"))
    
    st.markdown("🔹 **Thermal Conductivity k(T)** [W/(m·K)]")
    cond_1_s_expr = st.text_input("Solid: k = ", value="15.0 + 0.012*(T - 298.0)", key=uk("mat1", "cond_s_expr"))
    cond_1_l_expr = st.text_input("Liquid: k = ", value="30.0 - 0.012*(T - 1700.0)", key=uk("mat1", "cond_l_expr"))
    
    st.markdown("🔹 **Coefficient of Thermal Expansion α(T)** [1/K]")
    cte_1_s_expr = st.text_input("Solid: α = ", value="1.2e-6 + 2.1e-8*(T - 298.0)", key=uk("mat1", "cte_s_expr"))
    cte_1_l_expr = st.text_input("Liquid: α = ", value="0.0", key=uk("mat1", "cte_l_expr"))
    
    latent_1 = st.number_input("Latent Heat of Fusion L_f [J/kg]", value=2.7e5, step=1e3, format="%.0f", key=uk("mat1", "latent"))
    
    st.divider()
    st.markdown("### 🔧 Auto-Generated Fortran UDF – Material 1 Density")
    st.caption("This UDF is automatically generated from your expressions above and includes robust error handling.")
    
    dens_udf_1 = f"""!===============================================================================
! getDensity_{mat_1_name}.F90 - Temperature-Dependent Density UDF
! Generated for project: {project_name}
!===============================================================================
FUNCTION getDensity_{mat_1_name}(model, n, temp) RESULT(denst)
  USE DefUtils
  IMPLICIT NONE
  
  !-----------------------------------------------------------------------------
  ! Input/Output arguments
  !-----------------------------------------------------------------------------
  TYPE(Model_t) :: model          ! Elmer model structure
  INTEGER :: n                     ! Node index
  REAL(KIND=dp) :: temp            ! Current temperature [K]
  REAL(KIND=dp) :: denst           ! Density result [kg/m^3]
  REAL(KIND=dp) :: tscaler         ! Temperature scaler (usually 1.0)
  
  !-----------------------------------------------------------------------------
  ! Local variables
  !-----------------------------------------------------------------------------
  REAL(KIND=dp) :: refSolDenst, refLiqDenst, refTemp, alphas, alphal
  LOGICAL :: GotIt
  TYPE(ValueList_t), POINTER :: material

  !-----------------------------------------------------------------------------
  ! Get material parameter handle
  !-----------------------------------------------------------------------------
  material => GetMaterial()
  IF (.NOT. ASSOCIATED(material)) THEN
    CALL Fatal('getDensity', 'No material associated with current element')
  END IF

  !-----------------------------------------------------------------------------
  ! Read parameters from .sif file WITH ERROR HANDLING
  !-----------------------------------------------------------------------------
  refSolDenst = GetConstReal(material, 'Reference Density Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getDensity', 'Ref density solid not found in .sif')
  
  alphas = GetConstReal(material, 'Density Coeff Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getDensity', 'Density coeff solid not found in .sif')
  
  refLiqDenst = GetConstReal(material, 'Reference Density Liquid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getDensity', 'Ref density liquid not found in .sif')
  
  alphal = GetConstReal(material, 'Density Coefficient Liquid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getDensity', 'Density coeff liquid not found in .sif')

  refTemp = GetConstReal(material, 'Melting Point Temperature of {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getDensity', 'Melting point not found in .sif')
  
  tscaler = GetConstReal(material, 'Tscaler', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getDensity', 'Tscaler not found in .sif')

  !-----------------------------------------------------------------------------
  ! Compute density based on phase state
  !-----------------------------------------------------------------------------
  IF (refTemp <= temp) THEN
      CALL Warn('getDensity', 'Material 1 in liquid state at node.')
      ! Auto-generated from expression: {dens_1_l_expr}
      denst = {parse_expression_cached(dens_1_l_expr)}
  ELSE
      ! Auto-generated from expression: {dens_1_s_expr}
      denst = {parse_expression_cached(dens_1_s_expr)}
  END IF
  
END FUNCTION getDensity_{mat_1_name}
"""
    st.code(dens_udf_1, language="fortran")
    
    st.markdown("### 🔧 Auto-Generated Fortran UDF – Material 1 Thermal Conductivity")
    cond_udf_1 = f"""!===============================================================================
! getThermalConductivity_{mat_1_name}.F90 - Temperature-Dependent Conductivity UDF
!===============================================================================
FUNCTION getThermalConductivity_{mat_1_name}(model, n, temp) RESULT(thcondt)
  USE DefUtils
  IMPLICIT NONE
  
  TYPE(Model_t) :: model
  INTEGER :: n
  REAL(KIND=dp) :: temp, thcondt, tscaler
  REAL(KIND=dp) :: refSolThCond, refLiqThCond, refTemp, alphas, betas, alphal
  LOGICAL :: GotIt
  TYPE(ValueList_t), POINTER :: material

  material => GetMaterial()
  IF (.NOT. ASSOCIATED(material)) CALL Fatal('getThermalConductivity', 'No material found')

  refSolThCond = GetConstReal(material, 'Reference Thermal Conductivity Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalConductivity', 'Ref cond solid not found')
  
  alphas = GetConstReal(material, 'Cond Coeff As Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalConductivity', 'Coeff A solid not found')
  
  betas = GetConstReal(material, 'Cond Coeff Bs Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalConductivity', 'Coeff B solid not found')
  
  refLiqThCond = GetConstReal(material, 'Reference Thermal Conductivity Liquid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalConductivity', 'Ref cond liquid not found')
  
  alphal = GetConstReal(material, 'Cond Coeff Liquid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalConductivity', 'Coeff liquid not found')

  refTemp = GetConstReal(material, 'Melting Point Temperature of {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalConductivity', 'Melting point not found')
  
  tscaler = GetConstReal(material, 'Tscaler', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalConductivity', 'Tscaler not found')

  IF (refTemp <= temp) THEN
      CALL Warn('getThermalConductivity', 'Material 1 in liquid state.')
      thcondt = {parse_expression_cached(cond_1_l_expr)}
  ELSE
      thcondt = {parse_expression_cached(cond_1_s_expr)}
  END IF
  
END FUNCTION getThermalConductivity_{mat_1_name}
"""
    st.code(cond_udf_1, language="fortran")

    st.markdown("### 🔧 Auto-Generated Fortran UDF – Material 1 Thermal Expansivity")
    cte_udf_1 = f"""!===============================================================================
! getThermalExpansivity_{mat_1_name}.F90 - Temperature-Dependent CTE UDF
!===============================================================================
FUNCTION getThermalExpansivity_{mat_1_name}(model, n, temp) RESULT(expansivity)
  USE DefUtils
  IMPLICIT NONE
  
  TYPE(Model_t) :: model
  INTEGER :: n
  REAL(KIND=dp) :: temp, expansivity, tscaler
  REAL(KIND=dp) :: refSolExp, refTemp, alphas, betas
  LOGICAL :: GotIt
  TYPE(ValueList_t), POINTER :: material

  material => GetMaterial()
  IF (.NOT. ASSOCIATED(material)) CALL Fatal('getThermalExpansivity', 'No material found')

  refSolExp = GetConstReal(material, 'Reference Thermal Expansivity Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalExpansivity', 'Ref expansivity solid not found')
  
  alphas = GetConstReal(material, 'Thermal Expansivity Coeff As Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalExpansivity', 'Coeff A expansivity not found')
  
  betas = GetConstReal(material, 'Thermal Expansivity Coeff Bs Solid {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalExpansivity', 'Coeff B expansivity not found')

  refTemp = GetConstReal(material, 'Melting Point Temperature of {mat_1_name}', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalExpansivity', 'Melting point not found')
  
  tscaler = GetConstReal(material, 'Tscaler', GotIt)
  IF(.NOT. GotIt) CALL Fatal('getThermalExpansivity', 'Tscaler not found')

  IF (refTemp <= temp) THEN
      CALL Warn('getThermalExpansivity', 'Material 1 in liquid state.')
      expansivity = {parse_expression_cached(cte_1_l_expr)}
  ELSE
      expansivity = {parse_expression_cached(cte_1_s_expr)}
  END IF
  
END FUNCTION getThermalExpansivity_{mat_1_name}
"""
    st.code(cte_udf_1, language="fortran")

    # ====================== SPECIFIC ENTHALPY UDF SECTION ======================
    st.divider()
    with st.expander("🔥 Specific Enthalpy UDF Configuration (Equation-Based)", expanded=False):
        st.markdown('<div class="info-box">🔹 <strong>Equation-based enthalpy:</strong> Replace .dat lookup tables with an analytical expression for smoother Newton-Raphson convergence during phase change.</div>', unsafe_allow_html=True)
        st.markdown("""
        **Model**: `H(T) = (1/α) × [β₁·T + β₂·max(T-T₀,0) + β₃/(1+exp(-γ·(T-T₀))) + C]`
        - `α`: Scaling factor [kg/J] — inverse of overall multiplier
        - `β₁`: Linear sensible heat coefficient [J/(kg·K)]
        - `β₂`: Phase change contribution [J/(kg·K)]
        - `β₃`: Sigmoid amplitude for smooth latent heat [J/kg]
        - `γ`: Transition sharpness [1/K]
        - `T₀`: Reference/melting temperature [K]
        - `C`: Constant offset [J/kg]
        """)
        
        use_enthalpy_udf_1 = st.checkbox(
            "Use equation-based enthalpy for Material 1 (Recommended)", 
            value=st.session_state.use_enthalpy_udf_1, 
            key=uk("enth1", "use_udf")
        )
        st.session_state.use_enthalpy_udf_1 = use_enthalpy_udf_1
        
        if use_enthalpy_udf_1:
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                alpha_1 = st.number_input("α: Scaling Factor [kg/J]", value=5.13580e-2, format="%.3e", key=uk("enth1", "alpha"))
                beta1_1 = st.number_input("β₁: Linear Coeff [J/(kg·K)]", value=27.9467, format="%.4f", key=uk("enth1", "beta1"))
                beta2_1 = st.number_input("β₂: Phase Coeff [J/(kg·K)]", value=3.5064, format="%.4f", key=uk("enth1", "beta2"))
                beta3_1 = st.number_input("β₃: Sigmoid Amp [J/kg]", value=9995.0, format="%.1f", key=uk("enth1", "beta3"))
            with col_e2:
                gamma_1 = st.number_input("γ: Transition Sharpness [1/K]", value=0.086717, format="%.6f", key=uk("enth1", "gamma"))
                T0_1 = st.number_input("T₀: Reference Temp [K]", value=1700.0, step=0.01, key=uk("enth1", "T0"))
                C_1 = st.number_input("C: Constant Offset [J/kg]", value=-23485.0, format="%.1f", key=uk("enth1", "C"))
            
            st.markdown("**Preview Computed Enthalpy Values:**")
            preview_temps = [298.0, 1000.0, 1500.0, 1700.0, 1750.0, 2000.0]
            preview_data = []
            for T in preview_temps:
                H = compute_enthalpy_preview_cached(T, alpha_1, beta1_1, beta2_1, beta3_1, gamma_1, T0_1, C_1)
                preview_data.append({"T [K]": T, "H [J/kg]": f"{H:.2e}"})
            st.table(pd.DataFrame(preview_data))


# ==============================================================================
# TAB 2: HEAT SOURCE MODELS
# ==============================================================================
with tab_heat:
    st.header("🔦 Laser Heat Source Function")
    st.markdown('<div class="info-box">✅ <strong>Select from multiple heat source types.</strong> The "Pulsed Gaussian" model integrates temporally pulsed Gaussian heat source with harmonic modulation, apparent heat capacity phase change, and geometry-adjusted effective power.</div>', unsafe_allow_html=True)
    
    heat_type = st.selectbox(
        "Heat Source Type",
        ["Travelling Gaussian", "Fixed Gaussian", "Flat-Top (Super-Gaussian)", 
         "Double Ellipsoidal", "Pulsed Gaussian"],
        key=uk("heat", "type")
    )
    
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        beam_radius = st.number_input("Beam Radius r₀ [m]", value=35.0e-6, format="%.2e", key=uk("heat", "radius"))
        heat_coeff = st.number_input("Heat Coefficient [W/m²]", value=8.68e9, format="%.2e", key=uk("heat", "coeff"))
        speed_x = st.number_input("Scan Speed X [m/s]", value=0.0, step=0.1, key=uk("heat", "speedx"))
        speed_y = st.number_input("Scan Speed Y [m/s]", value=0.0, step=0.1, key=uk("heat", "speedy"))
    with col_h2:
        scan_dist = st.number_input("Scan Distance [m]", value=600.0e-6, format="%.2e", key=uk("heat", "dist"))
        init_x = st.number_input("Initial X Position [m]", value=0.0, format="%.2e", key=uk("heat", "initx"))
        init_y = st.number_input("Initial Y Position [m]", value=0.0, format="%.2e", key=uk("heat", "inity"))
        absorptance = st.number_input("Absorptance Ω [1/m]", value=8.5e7, format="%.2e", key=uk("heat", "absorp"))
    
    # --------------------------------------------------------------------------
    # PULSED GAUSSIAN HEAT SOURCE SPECIFIC PARAMETERS
    # --------------------------------------------------------------------------
    if heat_type == "Pulsed Gaussian":
        st.subheader("🔷 Pulsed Gaussian Heat Source Parameters")
        st.markdown("""
        Implements the coupled multiphysics model integrating:
        1. Temporally pulsed Gaussian heat source
        2. First three odd harmonics modulation during pulse-on
        3. Geometry-adjusted effective power for spherical/truncated geometries
        
        **Note on Power Calculation**: Since `Energy per pulse` is provided in **Joules (J)**, 
        the average power is calculated as `Pavg = Energy * Frequency`. (The `1e-3` multiplier 
        is omitted as it was intended for milliJoule inputs).
        """)
        
        col_pg1, col_pg2 = st.columns(2)
        with col_pg1:
            alpha_pg = st.number_input("Heat source half-width (Alpha) [m]", value=8.5e-4, format="%.2e", key=uk("heat", "alpha_pg"), help="Gaussian beam waist (half-width parameter)")
            pulse_width_pg = st.number_input("Laser pulsewidth [s]", value=6.0e-6, format="%.2e", key=uk("heat", "pulse_width_pg"), help="Duration of a single pulse (tau_pulse)")
            phase_shift_pg = st.number_input("Phase shift for sine wave", value=1.57, format="%.2f", key=uk("heat", "phase_shift_pg"), help="Phase shift (phi_shift), e.g., 1.57 for pi/2")
            rep_rate_pg = st.number_input("Repetition rate [Hz]", value=50.0, format="%.1f", key=uk("heat", "rep_rate_pg"), help="Pulse repetition rate (f_rep)")
            energy_pg = st.number_input("Energy per pulse in J", value=7.5e-3, format="%.2e", key=uk("heat", "energy_pg"), help="Experimental pulse energy in Joules (e.g., 7.5e-3 for 7.5 mJ)")
        with col_pg2:
            radius_ball_pg = st.number_input("Radius of solder ball [m]", value=50.0e-6, format="%.2e", key=uk("heat", "radius_ball_pg"), help="R_ball for effective power geometry adjustment")
            speed_pg = st.number_input("Heat source speed [m/s]", value=0.0, format="%.2e", key=uk("heat", "speed_pg"), help="Scan speed (0.0 for fixed)")
            dist_x_pg = st.number_input("Heat source distance x [m]", value=0.0, format="%.2e", key=uk("heat", "dist_x_pg"))
            init_x_pg = st.number_input("Heat source initial position x [m]", value=50.0e-6, format="%.2e", key=uk("heat", "init_x_pg"), help="Center of beam along x-axis")
            init_y_pg = st.number_input("y coordinate initial position [m]", value=50.0e-6, format="%.2e", key=uk("heat", "init_y_pg"), help="Center of beam along y-axis")

    # --------------------------------------------------------------------------
    # GENERATE HEAT SOURCE FORTRAN UDF BASED ON TYPE
    # --------------------------------------------------------------------------
    if heat_type == "Pulsed Gaussian":
        heat_udf = f"""!===============================================================================
! PulsedGaussianHeatSource.F90 - Pulsed Gaussian Heat Source for {project_name}
! 
! Integrates temporally pulsed Gaussian heat source with harmonic modulation.
! Reference: Coupled multiphysics model with apparent heat capacity phase change.
!
! Mathematical Formulation:
! G(r; alpha) = exp(-2 * r^2 / alpha^2)
! t_pulse_on = MOD(t, 1.0 / f_rep) < tau_pulse
! phi_harmonic(t) = SUM_{k=1,3,5} [ sin(k * 2 * PI * f_rep * t + phi_shift) / k ]
! P_avg = Energy * f_rep  (Energy is in Joules)
! P_effective = 2 * P_avg * (R_ball / alpha)^2
! C = 2 * P_effective / (PI * R_ball^2)
! I_laser = phi_harmonic(t) * C * G(r; alpha)
!===============================================================================
FUNCTION PulsedGaussianHeatSource(Model, n, t) RESULT(f)
  USE DefUtils
  IMPLICIT NONE
  
  !-----------------------------------------------------------------------------
  ! Input/Output arguments
  !-----------------------------------------------------------------------------
  TYPE(Model_t) :: Model          ! Elmer model structure
  INTEGER :: n                     ! Node index
  REAL(KIND=dp) :: t               ! Current time [s]
  REAL(KIND=dp) :: f               ! Heat flux result [W/m^2]

  !-----------------------------------------------------------------------------
  ! Local variables
  !-----------------------------------------------------------------------------
  INTEGER :: timestep, prevtimestep = -1
  INTEGER :: k
  REAL(KIND=dp) :: Alpha, Energy, Speed, xdist, xdist0
  REAL(KIND=dp) :: Time, x, y, z, s, r, yzero, phiharmonic
  REAL(KIND=dp) :: Frequency, PhaseShift, HarmonicSum
  REAL(KIND=dp) :: Pavg, Peffective, Coeff, Radiusball, PulseWidth
  REAL(KIND=dp), PARAMETER :: PI = 3.14159265358979323846_dp
  
  TYPE(Mesh_t), POINTER :: Mesh
  TYPE(ValueList_t), POINTER :: Params
  LOGICAL :: Found, NewTimestep
  
  !-----------------------------------------------------------------------------
  ! Persistent storage (retained between calls for efficiency)
  !-----------------------------------------------------------------------------
  SAVE Mesh, Params, prevtimestep, Time
  SAVE Alpha, Energy, Speed, xdist, xdist0, PulseWidth
  SAVE HarmonicSum, Pavg, Peffective, Coeff, Radiusball
  SAVE phiharmonic, Frequency, PhaseShift
  
  !-----------------------------------------------------------------------------
  ! Check if timestep changed - only re-read parameters when needed
  !-----------------------------------------------------------------------------
  timestep = GetTimestep()
  NewTimestep = (timestep /= prevtimestep)

  IF (NewTimestep) THEN
    Mesh => GetMesh()
    Params => Model % Simulation
    Time = GetTime()
    
    ! Read heat source parameters from .sif file WITH ERROR HANDLING
    Alpha = GetCReal(Params, 'Heat source half-width', Found)
    IF (.NOT. Found) CALL Fatal('PulsedGaussianHeatSource', 'Heat source half-width not defined')
    
    PulseWidth = GetCReal(Params, 'Laser pulsewidth', Found)
    IF (.NOT. Found) CALL Fatal('PulsedGaussianHeatSource', 'Laser pulsewidth not defined')
    
    PhaseShift = GetCReal(Params, 'Phase shift for sine wave', Found)
    IF (.NOT. Found) PhaseShift = 0.0_dp
    
    Energy = GetCReal(Params, 'Energy per pulse in J', Found)
    IF (.NOT. Found) CALL Fatal('PulsedGaussianHeatSource', 'Energy per pulse in J not defined')
    
    Radiusball = GetCReal(Params, 'Radius of solder ball', Found)
    IF (.NOT. Found) CALL Fatal('PulsedGaussianHeatSource', 'Radius of solder ball not defined')
    
    Speed = GetCReal(Params, 'Heat source speed', Found)
    IF (.NOT. Found) Speed = 0.0_dp
    
    xdist = GetCReal(Params, 'Heat source distance x', Found)
    IF (.NOT. Found) xdist = 0.0_dp
    
    xdist0 = GetCReal(Params, 'Heat source initial position x', Found)
    IF (.NOT. Found) xdist0 = 0.0_dp
    
    yzero = GetCReal(Params, 'y coordinate initial position', Found)
    IF (.NOT. Found) yzero = 0.0_dp
    
    Frequency = GetCReal(Params, 'Repetition rate', Found)
    IF (.NOT. Found) CALL Fatal('PulsedGaussianHeatSource', 'Repetition rate not defined')
    
    ! Pre-calculate steady coefficients
    Pavg = Energy * Frequency  ! Energy is in Joules, so no 1e-3 multiplier needed
    Peffective = 2.0_dp * Pavg * (Radiusball / Alpha)**2 
    Coeff = 2.0_dp * Peffective / (PI * Radiusball**2)
    
    prevtimestep = timestep
  END IF

  !-----------------------------------------------------------------------------
  ! Get current node coordinates
  !-----------------------------------------------------------------------------
  x = Mesh % Nodes % x(n)   
  y = Mesh % Nodes % y(n)   
  z = Mesh % Nodes % z(n)   

  !-----------------------------------------------------------------------------
  ! Compute travelling heat source center position (if Speed > 0)
  !-----------------------------------------------------------------------------
  s = xdist0 + Time * Speed  
  r = SQRT((x - s)**2 + (y - yzero)**2) 

  !-----------------------------------------------------------------------------
  ! Define the odd harmonics sine wave modulation function phi
  !-----------------------------------------------------------------------------
  HarmonicSum = 0.0_dp
  
  ! Check if current time is within the pulse-on window
  IF (MOD(t, 1.0_dp / Frequency) < PulseWidth) THEN
     ! Sum the first 3 odd harmonics (k = 1, 3, 5) while pulse is on
     ! Note: Using 2 * PI * Frequency * t to match the mathematical formulation
     DO k = 1, 5, 2  
         HarmonicSum = HarmonicSum + SIN(REAL(k, KIND=dp) * 2.0_dp * PI * Frequency * t + PhaseShift) / REAL(k, KIND=dp)
     END DO
     phiharmonic = HarmonicSum
  ELSE
     ! Enforce phi = 0 when pulse is off
     phiharmonic = 0.0_dp
  END IF
  
  !-----------------------------------------------------------------------------
  ! Compute final Gaussian heat flux distribution
  ! I_laser = phi_harmonic(t) * C * G(r; alpha)
  !-----------------------------------------------------------------------------
  f = phiharmonic * Coeff * EXP(-2.0_dp * r**2 / Alpha**2)
  
END FUNCTION PulsedGaussianHeatSource
"""
        heat_proc_name = "PulsedGaussianHeatSource"
        
    elif heat_type == "Travelling Gaussian":
        heat_udf = f"""!===============================================================================
! TravellingHeatSource.F90 - Standard Travelling Gaussian Heat Source
!===============================================================================
FUNCTION TravellingHeatSource(Model, n, t) RESULT(f)
  USE DefUtils
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  INTEGER :: n
  REAL(KIND=dp) :: t, f
  INTEGER :: timestep, prevtimestep = -1
  REAL(KIND=dp) :: Alpha, Coeff, xspeed, yspeed, Dist, Time, x, y, z, s1, s2, r, xzero, yzero, Omega
  TYPE(Mesh_t), POINTER :: Mesh
  TYPE(ValueList_t), POINTER :: Params
  LOGICAL :: Found, NewTimestep
  SAVE Mesh, Params, prevtimestep, time, Alpha, Coeff, xspeed, yspeed, Dist, Omega
  
  timestep = GetTimestep()
  NewTimestep = (timestep /= prevtimestep)
  IF(NewTimestep) THEN
    Mesh => GetMesh()
    Params => Model % Simulation
    time = GetTime()
    Alpha = GetCReal(Params, 'Heat source width')
    Coeff = GetCReal(Params, 'Heat source coefficient')
    xspeed = GetCReal(Params, 'Heat source speed x')
    yspeed = GetCReal(Params, 'Heat source speed y')
    Dist = GetCReal(Params, 'Heat source distance')
    xzero = GetCReal(Params, 'Heat source initial position x', Found)
    yzero = GetCReal(Params, 'Heat source initial position y', Found)
    Omega = GetCReal(Params, 'Absorptance of Surface Material')
    prevtimestep = timestep
  END IF
  x = Mesh % Nodes % x(n); y = Mesh % Nodes % y(n); z = Mesh % Nodes % z(n)
  s1 = xzero + time * xspeed; s2 = yzero + time * yspeed
  r = SQRT((x - s1)**2 + (y - s2)**2)
  f = Coeff * EXP(-2.0_dp * r**2 / Alpha**2 - Omega * ABS(z))
END FUNCTION TravellingHeatSource
"""
        heat_proc_name = "TravellingHeatSource"
        
    elif heat_type == "Fixed Gaussian":
        heat_udf = f"""!===============================================================================
! FixedHeatSource.F90 - Stationary Gaussian Heat Source
!===============================================================================
FUNCTION FixedHeatSource(Model, n, t) RESULT(f)
  USE DefUtils
  IMPLICIT NONE
  TYPE(Model_t) :: Model; INTEGER :: n; REAL(KIND=dp) :: t, f
  INTEGER :: timestep, prevtimestep = -1
  REAL(KIND=dp) :: Alpha, Coeff, Dist0, Time, x, y, z, r
  TYPE(Mesh_t), POINTER :: Mesh; TYPE(ValueList_t), POINTER :: Params
  LOGICAL :: Found, NewTimestep
  SAVE Mesh, Params, prevtimestep, time, Alpha, Coeff, Dist0
  
  timestep = GetTimestep(); NewTimestep = (timestep /= prevtimestep)
  IF(NewTimestep) THEN
    Mesh => GetMesh(); Params => Model % Simulation; time = GetTime()
    Alpha = GetCReal(Params, 'Heat source width')
    Coeff = GetCReal(Params, 'Heat source coefficient')
    Dist0 = GetCReal(Params, 'Heat source initial position x', Found)
    prevtimestep = timestep
  END IF
  x = Mesh % Nodes % x(n); y = Mesh % Nodes % y(n); z = Mesh % Nodes % z(n)
  r = x - Dist0
  f = Coeff * EXP(-2.0_dp * r**2 / Alpha**2)
END FUNCTION FixedHeatSource
"""
        heat_proc_name = "FixedHeatSource"
        
    elif heat_type == "Flat-Top (Super-Gaussian)":
        sgo = st.number_input("Super-Gaussian Order n", value=3.0, step=0.1, key=uk("heat", "sgo"))
        m1 = st.number_input("Amplitude Prefactor m₁", value=2.0, step=0.1, key=uk("heat", "m1"))
        m2 = st.number_input("Exponential Prefactor m₂", value=2.0, step=0.1, key=uk("heat", "m2"))
        rsgo = 1.0 / sgo if sgo > 0 else 0.3333
        st.info(f"Reciprocal 1/n = {rsgo:.4f} (auto-computed)")
        
        heat_udf = f"""!===============================================================================
! FlatTopHeatSource.F90 - Super-Gaussian Travelling Heat Source (Flat-Top)
!===============================================================================
FUNCTION FlatTopHeatSource(Model, n, t) RESULT(f)
  USE DefUtils
  IMPLICIT NONE
  TYPE(Model_t) :: Model; INTEGER :: n; REAL(KIND=dp) :: t, f
  INTEGER :: timestep, prevtimestep = -1
  REAL(KIND=dp) :: Alpha, Coeff, xspeed, yspeed, Dist, Time, x, y, z, s1, s2, r
  REAL(KIND=dp) :: xzero, yzero, sgo, m1, m2, rsgo
  TYPE(Mesh_t), POINTER :: Mesh; TYPE(ValueList_t), POINTER :: Params
  LOGICAL :: Found, NewTimestep
  SAVE Mesh, Params, prevtimestep, time, Alpha, Coeff, xspeed, yspeed, Dist
  SAVE xzero, yzero, sgo, m1, m2, rsgo
  
  timestep = GetTimestep(); NewTimestep = (timestep /= prevtimestep)
  IF(NewTimestep) THEN
    Mesh => GetMesh(); Params => Model % Simulation; time = GetTime()
    Alpha = GetCReal(Params, 'Heat source width')
    Coeff = GetCReal(Params, 'Heat source coefficient')
    xspeed = GetCReal(Params, 'Heat source speed x')
    yspeed = GetCReal(Params, 'Heat source speed y')
    Dist = GetCReal(Params, 'Heat source distance')
    xzero = GetCReal(Params, 'Heat source initial position x', Found)
    yzero = GetCReal(Params, 'Heat source initial position y', Found)
    sgo = GetCReal(Params, 'Super gaussian order n')
    rsgo = GetCReal(Params, 'reciproccal of Super gaussian order 1/n')
    m1 = GetCReal(Params, 'prefactor within amplitude term')
    m2 = GetCReal(Params, 'prefactor within exponential term')
    prevtimestep = timestep
  END IF
  x = Mesh % Nodes % x(n); y = Mesh % Nodes % y(n); z = Mesh % Nodes % z(n)
  s1 = xzero + time * xspeed; s2 = yzero + time * yspeed
  r = SQRT((x - s1)**2 + (y - s2)**2)
  ! Note: gamma() function requires intrinsic gamma or custom implementation in some Fortran compilers
  f = m1**rsgo * sgo * Coeff * EXP(-m2 * r**sgo / Alpha**sgo) / gamma(rsgo)
END FUNCTION FlatTopHeatSource
"""
        heat_proc_name = "FlatTopHeatSource"
        
    elif heat_type == "Double Ellipsoidal":
        a_front = st.number_input("Front Semi-Axis a_f [m]", value=50.0e-6, format="%.2e", key=uk("heat", "a_front"))
        b_axis = st.number_input("Transverse Semi-Axis b [m]", value=35.0e-6, format="%.2e", key=uk("heat", "b_axis"))
        a_rear = st.number_input("Rear Semi-Axis a_r [m]", value=75.0e-6, format="%.2e", key=uk("heat", "a_rear"))
        f_factor = st.number_input("Front Fraction f_f", value=0.6, step=0.1, min_value=0.0, max_value=1.0, key=uk("heat", "f_factor"))
        
        heat_udf = f"""!===============================================================================
! DoubleEllipsoidalHeatSource.F90 - Goldak Double Ellipsoidal Heat Source
!===============================================================================
FUNCTION DoubleEllipsoidalHeatSource(Model, n, t) RESULT(f)
  USE DefUtils
  IMPLICIT NONE
  TYPE(Model_t) :: Model; INTEGER :: n; REAL(KIND=dp) :: t, f
  INTEGER :: timestep, prevtimestep = -1
  REAL(KIND=dp) :: Af, Ar, B, Cf, Cr, Ff, Fr, Q, xspeed, yspeed, Dist, Time
  REAL(KIND=dp) :: x, y, z, s1, s2, xf, xr, yb, zb, ff, fr
  REAL(KIND=dp), PARAMETER :: PI = 3.14159265358979323846_dp
  TYPE(Mesh_t), POINTER :: Mesh; TYPE(ValueList_t), POINTER :: Params
  LOGICAL :: Found, NewTimestep
  SAVE Mesh, Params, prevtimestep, time, Af, Ar, B, Cf, Cr, Ff, Fr, Q, xspeed, yspeed, Dist
  
  timestep = GetTimestep(); NewTimestep = (timestep /= prevtimestep)
  IF(NewTimestep) THEN
    Mesh => GetMesh(); Params => Model % Simulation; time = GetTime()
    Af = GetCReal(Params, 'Front semi-axis a_f')
    Ar = GetCReal(Params, 'Rear semi-axis a_r')
    B = GetCReal(Params, 'Transverse semi-axis b')
    Cf = 2.0_dp * Af; Cr = 2.0_dp * Ar
    Ff = GetCReal(Params, 'Front fraction f_f')
    Fr = 1.0_dp - Ff
    Q = GetCReal(Params, 'Heat source coefficient')
    xspeed = GetCReal(Params, 'Heat source speed x')
    yspeed = GetCReal(Params, 'Heat source speed y')
    Dist = GetCReal(Params, 'Heat source distance')
    prevtimestep = timestep
  END IF
  x = Mesh % Nodes % x(n); y = Mesh % Nodes % y(n); z = Mesh % Nodes % z(n)
  s1 = time * xspeed; s2 = time * yspeed
  xf = x - s1; xr = s1 - x; yb = y - s2; zb = ABS(z)
  ff = Ff * 6.0_dp * SQRT(3.0_dp) / (PI * Af * B * Cf)
  fr = Fr * 6.0_dp * SQRT(3.0_dp) / (PI * Ar * B * Cr)
  IF (xf >= 0.0_dp) THEN
    f = Q * ff * EXP(-3.0_dp * (xf**2/Af**2 + yb**2/B**2 + zb**2/Cf**2))
  ELSE
    f = Q * fr * EXP(-3.0_dp * (xr**2/Ar**2 + yb**2/B**2 + zb**2/Cr**2))
  END IF
END FUNCTION DoubleEllipsoidalHeatSource
"""
        heat_proc_name = "DoubleEllipsoidalHeatSource"

    st.code(heat_udf, language="fortran")


# ==============================================================================
# TAB 3: LOOKUP TABLES (.dat files)
# ==============================================================================
with tab_tables:
    st.header("📊 Lookup Tables (.dat files)")
    st.markdown("Tab-separated files for viscosity and specific enthalpy vs. temperature. Used if equation-based enthalpy is disabled.")
    
    table_choice = st.selectbox(
        "Select Table to Edit",
        ["Viscosity – Material 1", "Specific Enthalpy – Material 1"],
        key=uk("table", "select")
    )
    
    table_configs = {
        "Viscosity – Material 1": {
            "default": pd.DataFrame({
                "Temperature_K": [300.0, 500.0, 1000.0, 1500.0, 1700.0, 1800.0],
                "Viscosity_Pas": [1.2e-3, 1.0e-3, 0.8e-3, 0.6e-3, 0.5e-3, 0.4e-3]
            }),
            "fname_prefix": "mu",
            "col1": "Temperature_K",
            "col2": "Viscosity_Pas",
            "key": "visc_1",
            "mat_selector": lambda: mat_1_name
        },
        "Specific Enthalpy – Material 1": {
            "default": pd.DataFrame({
                "Temperature_K": [300.0, 500.0, 1000.0, 1500.0, 1700.0, 1800.0],
                "Enthalpy_Jkg": [0.0, 1.54e5, 3.08e5, 4.62e5, 6.67e5, 7.90e5]
            }),
            "fname_prefix": "h",
            "col1": "Temperature_K",
            "col2": "Enthalpy_Jkg",
            "key": "enth_1",
            "mat_selector": lambda: mat_1_name
        }
    }
    
    config = table_configs[table_choice]
    session_key = f"table_data_{config['key']}"
    
    # Initialize session state for this table if not exists
    if st.session_state[session_key] is None:
        st.session_state[session_key] = config["default"].copy()
    
    edited_df = st.data_editor(
        st.session_state[session_key],
        num_rows="dynamic",
        key=uk("table", f"editor_{table_choice.replace(' ', '_')}"),
        column_config={
            config["col1"]: st.column_config.NumberColumn("T [K]", min_value=0, format="%.2f"),
            config["col2"]: st.column_config.NumberColumn(
                "Viscosity [Pa·s]" if "Viscosity" in table_choice else "Enthalpy [J/kg]",
                format="%.2e" if "Viscosity" in table_choice else "%.0f"
            )
        },
        hide_index=True
    )
    
    # ALWAYS update session state - this is critical for persistence
    st.session_state[session_key] = edited_df.copy()
    
    # Generate filename with current material name
    mat_name = config["mat_selector"]()
    fname = f"{config['fname_prefix']}_{mat_name.lower().replace('-', '_')}.dat"
    
    csv_content = edited_df.to_csv(sep='\t', index=False, float_format='%.6f')
    st.download_button(
        label=f"⬇️ Download {fname}",
        data=csv_content,
        file_name=fname,
        mime="text/tab-separated-values",
        key=uk("table", f"dl_{table_choice.replace(' ', '_')}")
    )
    
    # Show note about equation-based enthalpy option
    if "Specific Enthalpy" in table_choice:
        use_udf = st.session_state.use_enthalpy_udf_1
        if use_udf:
            st.markdown('<div class="success-box">✅ Equation-based enthalpy UDF is enabled for Material 1. The .dat table below is for reference only and will not be used in the generated .sif file.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-box">⚠️ Using .dat lookup table for enthalpy. Enable equation-based UDF in the Materials tab for a smoother analytical H(T) model.</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 4: PHYSICS & BOUNDARY CONDITIONS
# ==============================================================================
with tab_physics:
    st.header("⚙️ Physics Settings & Boundary Conditions")
    
    col_p1, col_p2 = st.columns(2)
    
    with col_p1:
        st.subheader("🕐 Time Stepping")
        coord_scaling = st.selectbox(
            "Coordinate Scaling",
            ["1.0e-6 (µm→m)", "1.0e-5 (10µm→m)", "1.0e-3 (mm→m)"],
            index=0, key=uk("phys", "coordscale")
        )
        dt_initial = st.number_input("Initial Δt [s]", value=1.0e-7, format="%.1e", key=uk("phys", "dtinit"))
        dt_main = st.number_input("Main Δt [s]", value=1.0e-5, format="%.1e", key=uk("phys", "dtmain"))
        n_steps_initial = st.number_input("Steps at initial Δt", value=1, min_value=1, key=uk("phys", "ninit"))
        n_steps_main = st.number_input("Steps at main Δt", value=60, min_value=1, key=uk("phys", "nmain"))
        bdf_order = st.selectbox("BDF Order", [1, 2, 3], index=1, key=uk("phys", "bdf"))
    
    with col_p2:
        st.subheader("📁 Output Settings")
        results_dir = st.text_input("Results Directory", value="./results/", key=uk("phys", "resdir"))
        output_file = st.text_input("Output File Base", value="invar.result", key=uk("phys", "outfile"))
        post_file = st.text_input("Post-Processing File", value="a.vtu", key=uk("phys", "postfile"))
        mesh_name = st.text_input("Mesh Database Name", value="Mesh_invar_external", key=uk("phys", "meshname"))
    
    st.divider()
    st.subheader("🔗 Boundary Conditions (Fixed Geometry Entities)")
    
    st.markdown("🔹 **Solids** (Body assignments - both use Material 1):")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        body1_solid = st.selectbox("Body 1 → Solid", SOLID_NAMES, index=0, key=uk("phys", "body1"))
    with col_s2:
        body2_solid = st.selectbox("Body 2 → Solid", SOLID_NAMES, index=1, key=uk("phys", "body2"))
    
    st.markdown("🔹 **Boundary Conditions** (select from fixed face list):")
    
    bc_fixed_defaults = ["Face_1leftfront", "Face_4bottomfront", "Face_7bottomback"]
    bc_fixed = safe_multiselect(
        "Fixed Displacement Faces (Zero Velocity/Displacement)",
        FACE_NAMES,
        default=bc_fixed_defaults,
        key=uk("phys", "bcfixed")
    )
    
    bc_conv_defaults = ["Face_2leftback", "Face_5topfront"]
    bc_conv = safe_multiselect(
        "Convective Cooling Faces (h=15 W/m²K, T∞=298K)",
        FACE_NAMES,
        default=bc_conv_defaults,
        key=uk("phys", "bcconv")
    )
    htc_value = st.number_input("Heat Transfer Coefficient h [W/m²K]", value=15.0, step=1.0, key=uk("phys", "htc"))
    
    bc_temp_defaults = ["Face_4bottomfront"]
    bc_temp = safe_multiselect(
        "Fixed Temperature Faces (T = 298 K)",
        FACE_NAMES,
        default=bc_temp_defaults,
        key=uk("phys", "bctemp")
    )
    
    heat_face = st.selectbox(
        "Laser Heat Flux Boundary",
        FACE_NAMES,
        index=4,
        key=uk("phys", "heatface")
    )
    
    st.divider()
    st.subheader("🌡️ Phase Change Settings")
    col_pc1, col_pc2 = st.columns(2)
    with col_pc1:
        mushy_width = st.number_input("Mushy Zone Width ±ΔT [K]", value=10.0, step=1.0, key=uk("phys", "mushy"))
        latent_release = st.checkbox("Check Latent Heat Release", value=True, key=uk("phys", "latentcheck"))
    with col_pc2:
        phase_model = st.selectbox("Phase Change Model", ["Spatial 2", "Spatial 1", "None"], index=0, key=uk("phys", "phasemodel"))


# ==============================================================================
# TAB 5: GENERATE FILES (ENHANCED PERSISTENCE & CACHING)
# ==============================================================================
with tab_generate:
    st.header("📥 Generate Complete Elmer Input Files")
    
    # Show persistent download section if content exists
    if st.session_state.generated_content and st.session_state.generation_timestamp:
        st.success(f"✅ Files generated at {st.session_state.generation_timestamp}!")
        st.markdown('<div class="download-section">', unsafe_allow_html=True)
        st.markdown("### 📥 Download Generated Files (Always Available)")
        st.markdown("*Downloads remain functional even after switching tabs or modifying non-critical parameters.*")
        
        # Regenerate button - separate from downloads
        if st.button("🔄 Regenerate Files with Current Settings", key="regenerate_btn", type="secondary"):
            st.session_state.generation_timestamp = None
            st.rerun()
        
        gc = st.session_state.generated_content  # Shortcut
        
        col_dl1, col_dl2, col_dl3 = st.columns(3)
        
        with col_dl1:
            st.download_button(
                label="📄 Download case.sif",
                data=gc['sif_content'],
                file_name=gc['sif_filename'],
                mime="text/plain",
                key="dl_sif_persistent"
            )
            st.download_button(
                label="🔧 getDensity.F90",
                data=gc['dens_f90_1'],
                file_name=f"getDensity_{gc['mat_1_name']}.F90",
                mime="text/plain",
                key="dl_dens_1_persistent"
            )
            st.download_button(
                label="🔧 getThermalConductivity.F90",
                data=gc['cond_f90_1'],
                file_name=f"getThermalConductivity_{gc['mat_1_name']}.F90",
                mime="text/plain",
                key="dl_cond_1_persistent"
            )
        
        with col_dl2:
            st.download_button(
                label="🔧 getThermalExpansivity.F90",
                data=gc['cte_f90_1'],
                file_name=f"getThermalExpansivity_{gc['mat_1_name']}.F90",
                mime="text/plain",
                key="dl_cte_1_persistent"
            )
            st.download_button(
                label="🔧 HeatSource.F90",
                data=gc['heat_f90'],
                file_name="DifferentTypeHeatSource.F90",
                mime="text/plain",
                key="dl_heat_persistent"
            )
            if gc.get('use_enthalpy_udf_1', False):
                st.download_button(
                    label="🔧 getSpecificEnthalpy.F90",
                    data=gc['enth_udf'],
                    file_name="getSpecificEnthalpy.F90",
                    mime="text/plain",
                    key="dl_enth_udf_persistent"
                )
        
        with col_dl3:
            # Lookup tables from persistent session state
            for table_key, label_prefix, fname_prefix in [
                ('visc_1_df', 'Viscosity – Material 1', 'mu'),
                ('enth_1_df', 'Specific Enthalpy – Material 1', 'h')
            ]:
                df = gc.get(table_key)
                mat = gc['mat_1_name']
                fname = f"{fname_prefix}_{mat.lower().replace('-', '_')}.dat"
                
                if df is not None and not df.empty:
                    content = df.to_csv(sep='\t', index=False, float_format='%.6f')
                else:
                    content = f"Temperature_K\\t{label_prefix.split('–')[1].strip()}_Unit\\n300.0\\t1.0e-3"
                
                st.download_button(
                    label=f"📊 {fname}",
                    data=content,
                    file_name=fname,
                    mime="text/tab-separated-values",
                    key=f"dl_table_{table_key}_persistent"
                )
        
        # ZIP bundling - persistent version
        st.divider()
        st.subheader("📦 One-Click Download: All Files as ZIP")
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(gc['sif_filename'], gc['sif_content'])
            zip_file.writestr(f"getDensity_{gc['mat_1_name']}.F90", gc['dens_f90_1'])
            zip_file.writestr(f"getThermalConductivity_{gc['mat_1_name']}.F90", gc['cond_f90_1'])
            zip_file.writestr(f"getThermalExpansivity_{gc['mat_1_name']}.F90", gc['cte_f90_1'])
            zip_file.writestr("DifferentTypeHeatSource.F90", gc['heat_f90'])
            
            if gc.get('use_enthalpy_udf_1', False):
                zip_file.writestr("getSpecificEnthalpy.F90", gc['enth_udf'])
            
            for table_key, prefix in [('visc_1_df', 'mu'), ('enth_1_df', 'h')]:
                df = gc.get(table_key)
                if df is not None and not df.empty:
                    mat = gc['mat_1_name']
                    fname = f"{prefix}_{mat.lower().replace('-', '_')}.dat"
                    content = df.to_csv(sep='\t', index=False, float_format='%.6f')
                    zip_file.writestr(fname, content)
        
        st.download_button(
            label="📦 Download ALL files as ZIP",
            data=zip_buffer.getvalue(),
            file_name=f"{gc.get('project_name', project_name)}_elmer_files.zip",
            mime="application/zip",
            key="download_all_zip_persistent"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Generate button
    if not st.session_state.generated_content or st.button("🔄 Generate All Files (New)", type="primary", use_container_width=True, key="generate_new_btn"):
        # === PRE-COMPUTE ALL SUBSTITUTION VALUES INTO DICTIONARY ===
        coord_val = coord_scaling.split()[0]
        timestep_intervals = f"{n_steps_initial} {n_steps_main}"
        timestep_sizes = f"{dt_initial:.1e} {dt_main:.1e}"
        heat_proc = heat_proc_name
        
        bc_fixed_idx = face_names_to_indices_cached(bc_fixed)
        bc_conv_idx = face_names_to_indices_cached(bc_conv)
        bc_temp_idx = face_names_to_indices_cached(bc_temp)
        heat_face_idx = re.search(r'Face_(\d+)', heat_face).group(1) if re.search(r'Face_(\d+)', heat_face) else "5"
        
        mat_1_name_lower = mat_1_name.lower().replace('-', '_')
        mat_1_melting_minus = mat_1_melting - mushy_width
        mat_1_melting_plus = mat_1_melting + mushy_width
        
        substitutions = {
            'project_name': project_name, 'author': author, 'date_str': date_str,
            'mesh_name': mesh_name, 'results_dir': results_dir,
            'post_file': post_file, 'output_file': output_file,
            'table_dir_visc': table_dir_visc, 'table_dir_enth': table_dir_enth,
            'coord_val': coord_val, 'timestep_intervals': timestep_intervals, 'timestep_sizes': timestep_sizes,
            'bdf_order': bdf_order,
            'mat_1_name': mat_1_name, 'mat_1_name_lower': mat_1_name_lower,
            'body1_solid': body1_solid, 'body2_solid': body2_solid,
            'mat_1_melting': mat_1_melting, 
            'mat_1_melting_minus': mat_1_melting_minus, 'mat_1_melting_plus': mat_1_melting_plus,
            'heat_type': heat_type, 'heat_proc': heat_proc,
            'beam_radius': beam_radius, 'heat_coeff': heat_coeff,
            'speed_x': speed_x, 'speed_y': speed_y, 'scan_dist': scan_dist,
            'init_x': init_x, 'init_y': init_y, 'absorptance': absorptance,
            'bc_fixed_len': len(bc_fixed), 'bc_conv_len': len(bc_conv), 'bc_temp_len': len(bc_temp),
            'bc_fixed_idx': bc_fixed_idx, 'bc_conv_idx': bc_conv_idx, 'bc_temp_idx': bc_temp_idx, 
            'heat_face_idx': heat_face_idx, 'htc_value': htc_value,
            'phase_model': phase_model, 'latent_check': 'True' if latent_release else 'False',
        }
        
        if heat_type == "Flat-Top (Super-Gaussian)":
            substitutions.update({'sgo': sgo, 'rsgo': rsgo, 'm1': m1, 'm2': m2})
        elif heat_type == "Double Ellipsoidal":
            substitutions.update({'a_front': a_front, 'a_rear': a_rear, 'b_axis': b_axis, 'f_factor': f_factor})
        elif heat_type == "Pulsed Gaussian":
            substitutions.update({
                'alpha_pg': alpha_pg, 'pulse_width_pg': pulse_width_pg, 'phase_shift_pg': phase_shift_pg,
                'rep_rate_pg': rep_rate_pg, 'energy_pg': energy_pg, 'radius_ball_pg': radius_ball_pg,
                'speed_pg': speed_pg, 'dist_x_pg': dist_x_pg, 'init_x_pg': init_x_pg, 'init_y_pg': init_y_pg
            })
        
        # === BUILD .sif FILE (COMPREHENSIVE TEMPLATE) ===
        sif_content = f"""    !===============================================================================
    ! Elmer solver input file for transient solid-liquid phase change with enthalpy formulation
    ! Geometry: Bilayer Invar (Solid_1front) / Invar (Solid_2back) - SINGLE MATERIAL 1
    ! Project: {project_name} | Author: {author} | Date: {date_str}
    ! Mesh supplied externally: {mesh_name}
    !===============================================================================

    Header
      CHECK KEYWORDS Warn
      Mesh DB "." "{mesh_name}"
      Include Path ""
      Results Directory "{results_dir}"
    End

    Simulation
      Max Output Level = 5
      Coordinate System = Cartesian 3D
      Coordinate Mapping(3) = 1 2 3
      Coordinate Scaling = {coord_val}
      Simulation Type = Transient
      Steady State Max Iterations = 5
      Output Intervals (2) = 1 1
      Timestep intervals (2) = {timestep_intervals}
      Timestep Sizes (2) = {timestep_sizes}
      Timestepping Method = BDF
      BDF Order = {bdf_order}
      Solver Input File = case.sif
      Post File = "{post_file}"
      Output File = "{output_file}"
      Binary Output = Logical True
      Use Mesh Names = True
      
      !=============================================================================
      ! Coefficients for input into the user defined subroutine {heat_proc}
      !=============================================================================
      Heat Source Width = Real {beam_radius}
      Heat Source Coefficient = Real {heat_coeff}
      Heat Source Speed x = Real {speed_x}
      Heat Source Speed y = Real {speed_y}
      Heat Source Distance = Real {scan_dist}
      Heat source initial position x = Real {init_x}
      Heat source initial position y = Real {init_y}
      Absorptance of Top Surface Material = Real {absorptance}
      Absorptance of Bottom Surface Material = Real {absorptance}
"""
        if heat_type == "Flat-Top (Super-Gaussian)":
            sif_content += f"""      Super gaussian order n = Real {sgo}
      reciproccal of Super gaussian order 1/n = Real {rsgo}
      prefactor within amplitude term = Real {m1}
      prefactor within exponential term = Real {m2}
"""
        elif heat_type == "Double Ellipsoidal":
            sif_content += f"""      Front semi-axis a_f = Real {a_front}
      Rear semi-axis a_r = Real {a_rear}
      Transverse semi-axis b = Real {b_axis}
      Front fraction f_f = Real {f_factor}
"""
        elif heat_type == "Pulsed Gaussian":
            sif_content += f"""      ! Pulsed Gaussian Specific Parameters
      Heat source half-width = Real {alpha_pg}
      Laser pulsewidth = Real {pulse_width_pg}
      Phase shift for sine wave = Real {phase_shift_pg}
      Repetition rate = Real {rep_rate_pg}
      Energy per pulse in J = Real {energy_pg}
      Radius of solder ball = Real {radius_ball_pg}
      Heat Source Speed = Real {speed_pg}
      Heat source distance x = Real {dist_x_pg}
      Heat source initial position x = Real {init_x_pg}
      y coordinate initial position = Real {init_y_pg}
"""
        
        sif_content += f"""      Mesh Levels = 1
    End

    Constants
      Gravity(4) = 0 -1 0 9.82
      Stefan Boltzmann = 5.67e-08
      Permittivity of Vacuum = 8.8542e-12
      Boltzmann Constant = 1.3807e-23
      Unit Charge = 1.602e-19
    End

    !=============================================================================
    ! BODY DEFINITIONS (Both assigned to Material 1)
    !=============================================================================
    Body 1
      Target Bodies(1) = 1
      Name = "{body1_solid}"
      Equation = 1
      Material = 1
      Body Force = 1
      Initial condition = 1
    End

    Body 2
      Target Bodies(1) = 2
      Name = "{body2_solid}"
      Equation = 1
      Material = 1
      Body Force = 1
      Initial condition = 1
    End
    
    !=============================================================================
    ! SOLVER DEFINITIONS
    !=============================================================================
    Solver 1
      Equation = Heat Equation
      Procedure = "HeatSolve" "HeatSolver"
      Calculate Loads = True
      Variable = Temperature
      Exec Solver = Always
      Stabilize = True
      Bubbles = True
      Lumped Mass Matrix = False
      Optimize Bandwidth = True
      Steady State Convergence Tolerance = 1.0e-6
      Nonlinear System Convergence Tolerance = 1.0e-7
      Nonlinear System Max Iterations = 10
      Nonlinear System Newton After Iterations = 3
      Nonlinear System Newton After Tolerance = 1.0e-3
      Nonlinear System Relaxation Factor = 0.6
      Linear System Solver = Iterative
      Linear System Iterative Method = BiCGStab
      Linear System Max Iterations = 500
      Linear System Convergence Tolerance = 1.0e-10
      Linear System Preconditioning = ILU0
      Linear System ILUT Tolerance = 1.0e-3
      Linear System Abort Not Converged = False
      Linear System Residual Output = 1
      Linear System Precondition Recompute = 1
    End

    Solver 2
      Equation = Navier-Stokes
      Variable = Flow Solution[Velocity:3 Pressure:1]
      Procedure = "FlowSolve" "FlowSolver"
      Calculate Loads = True
      Exec Solver = Always
      Stabilize = True
      Bubbles = False
      Lumped Mass Matrix = False
      Optimize Bandwidth = True
      Steady State Convergence Tolerance = 1.0e-4
      Nonlinear System Convergence Tolerance = 1.0e-7
      Nonlinear System Max Iterations = 5
      Nonlinear System Newton After Iterations = 3
      Nonlinear System Newton After Tolerance = 1.0e-3
      Nonlinear System Relaxation Factor = 0.6
      Linear System Solver = Iterative
      Linear System Iterative Method = BiCGStab
      Linear System Max Iterations = 500
      Linear System Convergence Tolerance = 1.0e-10
      Linear System Preconditioning = ILU0
      Linear System ILUT Tolerance = 1.0e-3
      Linear System Abort Not Converged = False
      Linear System Residual Output = 1
      Linear System Precondition Recompute = 1
    End
    
    Solver 3
      Equation = "LinearDisp"
      Procedure = "StressSolve" "StressSolver"
      Variable = "Displacement"
      Variable DOFs = Integer 3
      Calculate Stresses = TRUE
      Calculate Strains = TRUE
      Calculate Principal = Logical TRUE
      Linear System Solver = Direct
      Linear System Symmetric = Logical True
      Linear System Scaling = Logical False
      Linear System Iterative Method = BiCGStab
      Linear System Direct Method = UMFPACK
      Linear System Convergence Tolerance = 1.0e-8
      Linear System Max Iterations = 200
      Linear System Preconditioning = ILU2
      Nonlinear System Convergence Tolerance = Real 1.0e-7
      Nonlinear System Max Iterations = Integer 1
      Nonlinear System Relaxation Factor = Real 1
      Steady State Convergence Tolerance = 1.0e-6
      Optimize Bandwidth = True
    End
    
    Solver 4
      Exec Solver = never
      Equation = SaveLine
      Procedure = "SaveData" "SaveLine"
      Filename = f.dat
    End

    !=============================================================================
    ! EQUATION DEFINITIONS
    !=============================================================================
    Equation 1
      Name = "Equation 1"
      Phase Change Model = {phase_model}
      Check Latent Heat Release = {latent_check}
      Convection = Computed
      Navier-Stokes = True
      NS Convect = True
      Active Solvers(3) = 1 2 3
    End

    !=============================================================================
    ! MATERIAL 1 DEFINITION (INVAR - APPLIED TO BOTH SOLIDS)
    !=============================================================================
    Material 1
      Name = "{mat_1_name}"
      
      !--- Elasticity + Plasticity Computation Purpose ---
      Youngs Modulus = Variable vonMises
      Procedure "plasticityMaterialModel" "getPlasticity"
      Isotropic elastic modulus in elastic regime in Pa = Real 140.0e9
      Yield strength of the alloy materials in Pa = Real 249.0e6
      Strength coefficient in Ramberg-Osgood equation = Real 381.08e6
      Reciprocal of strain hardening coefficient = Real 9.7087
      Poisson Ratio = Real 0.29
      Reference Temperature = 298.0
      
      !--- Thermal Expansivity ---
      Heat Expansion Coefficient = Variable Temperature
      Procedure "getThermalExpansivity" "getThermalExpansivity"
      Reference Thermal Expansivity Solid {mat_1_name} = Real 1.2e-6
      Thermal Expansivity Coeff As Solid {mat_1_name} = Real 2.1e-8
      
      !--- Viscosity ---
      Viscosity = Variable Temperature
    Real
      include {table_dir_visc}mu_{mat_1_name_lower}.dat
    End
"""
        
        # --- SPECIFIC ENTHALPY SECTION FOR MATERIAL 1 ---
        if st.session_state.use_enthalpy_udf_1:
            sif_content += f"""      !--- Equation-Based Specific Enthalpy ---
      Specific Enthalpy = Variable Temperature
      Procedure "getSpecificEnthalpy" "getSpecificEnthalpy"
      Enthalpy Scaling Factor alpha = Real {alpha_1}
      Enthalpy Linear Coeff beta1 = Real {beta1_1}
      Enthalpy Phase Coeff beta2 = Real {beta2_1}
      Enthalpy Sigmoid Amp beta3 = Real {beta3_1}
      Enthalpy Transition Gamma = Real {gamma_1}
      Enthalpy Reference Temperature T0 = Real {T0_1}
      Enthalpy Constant Offset C = Real {C_1}
"""
        else:
            sif_content += f"""      !--- Lookup Table Specific Enthalpy ---
      Specific Enthalpy = Variable Temperature
    Real
      include {table_dir_enth}h_{mat_1_name_lower}.dat
    End
"""
        
        # --- CONTINUE MATERIAL 1 BLOCK ---
        sif_content += f"""      !--- Phase Change & Thermal Properties ---
      Phase Change Intervals(2,1) = {mat_1_melting_minus} {mat_1_melting_plus}
      Compressibility Model = Incompressible
      Reference Pressure = 0
      Specific Heat Ratio = 1.4
      
      Heat Conductivity = Variable Temperature
      Procedure "getFilmThermalConductivity" "getThermalConductivity"
      Reference Thermal Conductivity Solid {mat_1_name} = Real 15.0
      Cond Coeff As Solid {mat_1_name} = Real 0.012
      Reference Thermal Conductivity Liquid {mat_1_name} = Real 30.0
      Cond Coeff Liquid {mat_1_name} = Real -0.012
      Melting Point Temperature of {mat_1_name} = Real {mat_1_melting}
      
      Density = Variable Temperature
      Procedure "getFilmDensity" "getDensity"
      Reference Density Solid {mat_1_name} = Real 8100.0
      Density Coeff Solid {mat_1_name} = Real -0.11
      Reference Density Liquid {mat_1_name} = Real 7500.0
      Density Coefficient Liquid {mat_1_name} = Real -0.28
      Tscaler = Real 1.0
    End
    
    !=============================================================================
    ! BODY FORCES & INITIAL CONDITIONS
    !=============================================================================
    Body Force 1
      Name = "Natural convection"
      Boussinesq = True
    End

    Initial Condition 1
      Name = "InitialCondition 1"
      Velocity 1 = 0
      Velocity 2 = 0
      Velocity 3 = 0
      Pressure = 0
      Temperature = 298.0
      Displacement 1 = 0
      Displacement 2 = 0
      Displacement 3 = 0
    End

    !=============================================================================
    ! BOUNDARY CONDITIONS
    !=============================================================================
    Boundary Condition 1
      Name = "Fixed Displacement Faces"
      Target Boundaries({len(bc_fixed)}) = {bc_fixed_idx}
      Displacement 1 = 0
      Displacement 2 = 0
      Displacement 3 = 0
      Noslip wall BC = True
      Save Scalars = Logical True
    End
    
    Boundary Condition 2
      Name = "Convective Cooling Faces"
      Target Boundaries({len(bc_conv)}) = {bc_conv_idx}
      External Temperature = 298.0
      Heat Transfer Coefficient = {htc_value}
      Noslip wall BC = True
      Save Scalars = Logical True
    End

    Boundary Condition 3
      Name = "Bottom Fixed Temperature"
      Target Boundaries({len(bc_temp)}) = {bc_temp_idx}
      External Temperature = 298.0
      Noslip wall BC = True
      Displacement 1 = 0
      Displacement 2 = 0
      Displacement 3 = 0
      Save Scalars = Logical True
      Temperature = 298.0
    End

    Boundary Condition 4
      Name = "Top Laser Heat Flux"
      Target Boundaries(1) = {heat_face_idx}
      Heat Flux = Variable time
      Real Procedure "DifferentTypeHeatSource" "{heat_proc}"
      Save Line = True
    End
"""
        
        # === PREPARE FORTRAN UDF FILES ===
        dens_f90_1 = extract_udf_code_cached(dens_udf_1)
        cond_f90_1 = extract_udf_code_cached(cond_udf_1)
        cte_f90_1 = extract_udf_code_cached(cte_udf_1)
        heat_f90 = heat_udf
        
        # Prepare Enthalpy UDF if enabled
        enth_udf = ""
        if st.session_state.use_enthalpy_udf_1:
            enth_udf = f"""!===============================================================================
! getSpecificEnthalpy.F90 - Equation-based Specific Enthalpy UDF
! Generated for project: {project_name}
!===============================================================================
FUNCTION getSpecificEnthalpy(model, n, temp) RESULT(enthalpy)
  USE DefUtils
  IMPLICIT NONE
  TYPE(Model_t) :: model
  INTEGER :: n
  REAL(KIND=dp) :: temp, enthalpy
  INTEGER :: timestep, prevtimestep = -1
  REAL(KIND=dp) :: alpha, beta1, beta2, beta3, gamma, T0, const_offset
  REAL(KIND=dp) :: linear_term, phase_term, sigmoid_term, bracket_sum
  REAL(KIND=dp) :: exp_arg, exp_val, denom, max_val
  TYPE(ValueList_t), POINTER :: material
  LOGICAL :: GotIt

  SAVE prevtimestep, alpha, beta1, beta2, beta3, gamma, T0, const_offset

  material => GetMaterial()
  IF (.NOT. ASSOCIATED(material)) CALL Fatal('getSpecificEnthalpy', 'No material associated')

  timestep = GetTimestep()
  IF (timestep /= prevtimestep) THEN
    alpha = GetConstReal(material, 'Enthalpy Scaling Factor alpha', GotIt)
    IF (.NOT. GotIt) CALL Fatal('getSpecificEnthalpy', 'alpha not defined')
    beta1 = GetConstReal(material, 'Enthalpy Linear Coeff beta1', GotIt)
    IF (.NOT. GotIt) CALL Fatal('getSpecificEnthalpy', 'beta1 not defined')
    beta2 = GetConstReal(material, 'Enthalpy Phase Coeff beta2', GotIt)
    IF (.NOT. GotIt) CALL Fatal('getSpecificEnthalpy', 'beta2 not defined')
    beta3 = GetConstReal(material, 'Enthalpy Sigmoid Amp beta3', GotIt)
    IF (.NOT. GotIt) CALL Fatal('getSpecificEnthalpy', 'beta3 not defined')
    gamma = GetConstReal(material, 'Enthalpy Transition Gamma', GotIt)
    IF (.NOT. GotIt) CALL Fatal('getSpecificEnthalpy', 'gamma not defined')
    T0 = GetConstReal(material, 'Enthalpy Reference Temperature T0', GotIt)
    IF (.NOT. GotIt) CALL Fatal('getSpecificEnthalpy', 'T0 not defined')
    const_offset = GetConstReal(material, 'Enthalpy Constant Offset C', GotIt)
    IF (.NOT. GotIt) CALL Fatal('getSpecificEnthalpy', 'C not defined')
    prevtimestep = timestep
  END IF

  linear_term = beta1 * temp
  max_val = temp - T0
  phase_term = beta2 * max_val IF (max_val > 0.0_dp) ELSE 0.0_dp
  
  exp_arg = -gamma * (temp - T0)
  IF (exp_arg > 700.0_dp) THEN
    sigmoid_term = 0.0_dp
  ELSE IF (exp_arg < -700.0_dp) THEN
    sigmoid_term = beta3
  ELSE
    exp_val = EXP(exp_arg)
    denom = 1.0_dp + exp_val
    sigmoid_term = beta3 / denom IF (denom > 1.0e-300_dp) ELSE beta3
  END IF
  
  bracket_sum = linear_term + phase_term + sigmoid_term + const_offset
  enthalpy = bracket_sum / alpha
  
END FUNCTION getSpecificEnthalpy
"""
        
        # === STORE ALL GENERATED CONTENT IN SESSION STATE ===
        st.session_state.generated_content = {
            'sif_content': sif_content,
            'sif_filename': sif_filename,
            'dens_f90_1': dens_f90_1, 
            'cond_f90_1': cond_f90_1,
            'cte_f90_1': cte_f90_1,
            'heat_f90': heat_f90,
            'enth_udf': enth_udf,
            'use_enthalpy_udf_1': st.session_state.use_enthalpy_udf_1,
            'mat_1_name': mat_1_name,
            'table_dir_visc': table_dir_visc, 
            'table_dir_enth': table_dir_enth,
            'project_name': project_name,
            'visc_1_df': st.session_state.table_data_visc_1.copy() if st.session_state.table_data_visc_1 is not None else pd.DataFrame(),
            'enth_1_df': st.session_state.table_data_enth_1.copy() if st.session_state.table_data_enth_1 is not None else pd.DataFrame(),
        }
        
        st.session_state.generation_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.success(f"✅ Files generated successfully at {st.session_state.generation_timestamp}!")
        st.rerun()  # Re-run to show persistent download section
    
    # Instructions expander (always visible)
    with st.expander("📋 How to Compile & Run", expanded=True):
        gc = st.session_state.generated_content
        mat_1_lower = gc.get('mat_1_name', mat_1_name).lower().replace('-', '_') if gc else mat_1_name.lower().replace('-', '_')
        
        enth_note_1 = "✅ Equation-based UDF" if gc.get('use_enthalpy_udf_1', False) else "📊 Lookup table (.dat)"
        
        st.markdown(f"""
        **Directory Structure:**
        ```text
        {project_name}/
        ├── {sif_filename}                 # Main Elmer input file
        ├── {mesh_name}.mesh              # Your externally-supplied mesh
        ├── {fortran_dir}
        │   ├── getDensity_{mat_1_name}.F90
        │   ├── getThermalConductivity_{mat_1_name}.F90
        │   ├── getThermalExpansivity_{mat_1_name}.F90
        │   ├── DifferentTypeHeatSource.F90
        │   └── getSpecificEnthalpy.F90    # [If equation-based enthalpy enabled]
        ├── {table_dir_visc}
        │   └── mu_{mat_1_lower}.dat
        └── {table_dir_enth}
            └── h_{mat_1_lower}.dat        # [{enth_note_1}]
        ```
        
        **Compilation & Execution Steps:**
        ```bash
        # 1. Navigate to project directory
        cd {project_name}
        
        # 2. Compile Fortran UDFs
        elmerfem -c {fortran_dir}getDensity_{mat_1_name}.F90
        elmerfem -c {fortran_dir}getThermalConductivity_{mat_1_name}.F90
        elmerfem -c {fortran_dir}getThermalExpansivity_{mat_1_name}.F90
        elmerfem -c {fortran_dir}DifferentTypeHeatSource.F90
        
        # 3. Compile Enthalpy UDF (if enabled)
        # elmerfem -c {fortran_dir}getSpecificEnthalpy.F90
        
        # 4. Run Elmer Solver
        ElmerSolver {sif_filename}
        ```
        
        **Key Features Implemented:**
        - ✅ **Single Material Configuration**: Material 1 (Invar) cleanly applied to both `Solid_1front` and `Solid_2back`.
        - ✅ **Pulsed Gaussian Heat Source**: Full implementation of temporally pulsed Gaussian with 3 odd harmonics, geometry-adjusted effective power, and correct Joule-based average power calculation (`Pavg = Energy * Frequency`).
        - ✅ **Linked UDF System**: UI expressions auto-update Fortran code with robust `GetConstReal` error handling.
        - ✅ **Equation-based Enthalpy**: Optional analytical H(T) model with 7 coefficients for superior Newton-Raphson convergence.
        - ✅ **Persistent Session State**: Downloads NEVER break; all files remain accessible across tab switches.
        - ✅ **ZIP Bundling**: One-click download of the entire project structure.
        """)

# ==============================================================================
# FOOTER & DEBUG INFO
# ==============================================================================
st.markdown("---")
st.markdown("""
**💡 Pro Tips:**
- 🔄 **Session state persistence**: Download any file without losing access to others.
- 💾 **Intelligent caching**: Expensive computations cached for 1 hour to improve UI responsiveness.
- 📦 **ZIP bundling**: Cleanest UX for distributing complete project files to HPC clusters.
- 🔥 **Enthalpy UDF**: Strongly recommended to enable the equation-based model for smoother solver convergence during phase change.

**🔗 Resources:**
- [Elmer FEM Documentation](https://www.elmerfem.org)
- [Fortran UDF Guide (DefUtils)](https://github.com/ElmerCSC/elmerfem/blob/devel/fem/src/modules/DefUtils.F90)
""")

# Debug Info (Optional, for advanced users)
if st.checkbox("Show Debug Info", key=uk("debug", "show")):
    debug_info = {
        "project": project_name,
        "material": {"name": mat_1_name, "melting_point": mat_1_melting},
        "mesh": mesh_name,
        "heat_source": heat_type,
        "timesteps": {"initial": dt_initial, "main": dt_main, "total": n_steps_initial + n_steps_main},
        "geometry": {"solids": SOLID_NAMES, "faces": FACE_NAMES},
        "boundary_conditions": {
            "fixed": bc_fixed,
            "convective": bc_conv,
            "fixed_temp": bc_temp,
            "heat_flux": heat_face
        },
        "enthalpy_udf": {
            "material_1_enabled": st.session_state.use_enthalpy_udf_1,
            "coefficients_1": {
                "alpha": alpha_1, "beta1": beta1_1, "beta2": beta2_1, 
                "beta3": beta3_1, "gamma": gamma_1, "T0": T0_1, "C": C_1
            } if st.session_state.use_enthalpy_udf_1 else None,
        },
        "session_state": {
            "has_generated_content": bool(st.session_state.generated_content),
            "generation_timestamp": st.session_state.generation_timestamp,
            "table_data_keys": [k for k in st.session_state.keys() if "table_data" in k]
        }
    }
    st.json(debug_info)
