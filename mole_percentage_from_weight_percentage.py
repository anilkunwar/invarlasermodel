def weight_to_mole_percentage(weight_Ni):
    """
    Convert weight percentage of Ni in Fe-Ni alloy to mole percentage.
    
    Parameters:
        weight_Ni (float): Nickel weight percentage (0-100)
    
    Returns:
        float: Nickel mole percentage
    """
    atomic_weight_Fe = 55.845
    atomic_weight_Ni = 58.693

    weight_Fe = 100 - weight_Ni
    moles_Ni = weight_Ni / atomic_weight_Ni
    moles_Fe = weight_Fe / atomic_weight_Fe

    mole_percentage_Ni = (moles_Ni / (moles_Ni + moles_Fe)) * 100
    return mole_percentage_Ni

if __name__ == "__main__":
    weight_Ni = float(input("Enter Nickel weight percentage: "))
    mole_Ni = weight_to_mole_percentage(weight_Ni)
    print(f"Nickel mole percentage: {mole_Ni:.2f}%")

