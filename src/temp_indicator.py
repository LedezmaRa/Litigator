def calculate_volume_trend(df: pd.DataFrame, period: int = 4) -> pd.Series:
    """
    Calculates the trend of volume over the last N periods.
    Returns the slope of the linear regression line for volume.
    Positive slope = Increasing volume.
    Negative slope = Decreasing volume.
    """
    # Simple slope calculation: (Last - First) / Period ? 
    # Or linear regression slope?
    # Spec says: "Increasing last 4 weeks".
    # Let's use a rolling correlation or slope.
    # Simpler: Rolling slope of Normalized Volume.
    
    # Let's use a simpler proxy: Count how many of the last N bars had volume > prev bar?
    # Spect says: "Increasing trend".
    # Implementation: Rolling linear regression slope.
    
    def calc_slope(y):
        if len(y) < 2: return 0.0
        x = np.arange(len(y))
        # Slope formula: (N*Sum(xy) - Sum(x)*Sum(y)) / (N*Sum(x^2) - (Sum(x))^2)
        n = len(y)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_xx = np.sum(x * x)
        
        denom = (n * sum_xx - sum_x * sum_x)
        if denom == 0: return 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / denom
        return slope

    res = df['Volume'].rolling(window=period).apply(calc_slope, raw=True)
    return res
