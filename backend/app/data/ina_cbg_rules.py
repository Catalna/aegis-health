from typing import Dict, Tuple, Optional
from pydantic import BaseModel
import re

class CBGGroup(BaseModel):
    code: str
    name: str
    base_tariff: float
    severity_multiplier: float

# A highly simplified version of the INA-CBG grouper logic for demonstration purposes.
DIAGNOSIS_TO_CBG_MAPPING = {
    "J18": CBGGroup(code="J-4-16", name="PNEUMONIA", base_tariff=3500000, severity_multiplier=1.4),
    "J44": CBGGroup(code="J-4-20", name="COPD", base_tariff=4200000, severity_multiplier=1.35),
    "I21": CBGGroup(code="I-4-10", name="ACUTE MYOCARDIAL INFARCTION", base_tariff=24000000, severity_multiplier=1.6),
    "I10": CBGGroup(code="I-4-15", name="HYPERTENSION", base_tariff=5000000, severity_multiplier=1.2),
    "E11": CBGGroup(code="E-4-10", name="TYPE 2 DIABETES MELLITUS", base_tariff=2000000, severity_multiplier=1.3),
    "K35": CBGGroup(code="K-1-14", name="ACUTE APPENDICITIS", base_tariff=7500000, severity_multiplier=1.5),
    "O80": CBGGroup(code="O-6-10", name="NORMAL DELIVERY", base_tariff=1800000, severity_multiplier=1.2),
    "N18": CBGGroup(code="N-4-10", name="CHRONIC KIDNEY DISEASE", base_tariff=8500000, severity_multiplier=1.4),
    "C50": CBGGroup(code="C-4-10", name="BREAST CANCER", base_tariff=35000000, severity_multiplier=1.8),
    "S72": CBGGroup(code="S-4-10", name="FEMUR FRACTURE", base_tariff=28000000, severity_multiplier=1.5),
}

# Simplified additive factor to the base tariff before severity multiplier.
PROCEDURE_ADD_ONS = {
    "36.1": 45000000, # CABG
    "36.10": 45000000, # CABG specific
    "47.0": 5000000,  # Appendectomy
    "39.95": 2500000, # Hemodialysis
    "85.41": 15000000, # Mastectomy
    "81.51": 35000000, # Hip replacement
}

def calculate_expected_tariff(
    diagnosis_primary: str, 
    procedure_codes: list[str], 
    severity_level: int
) -> Optional[Tuple[str, str, float]]:
    """
    Returns (cbg_code, cbg_name, expected_tariff) if diagnosis is mapped, else None.
    """
    # Try to find a match (allowing for sub-codes like J18.9)
    primary_base = diagnosis_primary.split('.')[0] if '.' in diagnosis_primary else diagnosis_primary
    
    cbg_info = DIAGNOSIS_TO_CBG_MAPPING.get(primary_base)
    if not cbg_info:
        return None
        
    base_amount = cbg_info.base_tariff
    
    # Add procedure costs
    for proc in procedure_codes:
        proc_base = proc.split('.')[0] if '.' in proc else proc
        # Check direct or prefix match
        for key, addon in PROCEDURE_ADD_ONS.items():
            if proc.startswith(key):
                base_amount += addon
                break
                
    # Apply severity multiplier
    # Severity in data might be 1-4. 
    # 1: 1.0x, 2: 1.0 + multiplier/2, 3: 1.0 + multiplier, 4: 1.0 + multiplier * 1.5
    multiplier = 1.0
    if severity_level == 2:
        multiplier = 1.0 + ((cbg_info.severity_multiplier - 1.0) / 2)
    elif severity_level == 3:
        multiplier = cbg_info.severity_multiplier
    elif severity_level >= 4:
        multiplier = cbg_info.severity_multiplier * 1.5
        
    expected_tariff = base_amount * multiplier
    
    # Construct a simplified output code
    out_code = f"{cbg_info.code}-{severity_level}"
    
    return out_code, cbg_info.name, round(expected_tariff, 2)
