<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=4.177s | action=fetch the FRED series VIXCLS (daily VIX -->
<!-- reason:  -->

To address your request, I will use the `pandas_datareader` library to fetch the **VIXCLS** series from FRED, define the threshold at 18, and analyze the clustering of "Out-of-Sample" (OOS) days.

Since you mentioned a "top contender" (implying a specific strategy or model performance), I have structured the code below to allow you to input your OOS date list. I will then calculate the distribution and perform a **Chi-Squared test** to determine if the clustering in the $VIX \ge 18$ regime is statistically significant compared to the $VIX < 18$ regime.

### Python Implementation

```python
import pandas as pd
import pandas_datareader.data as web
from scipy.stats import chisquare
import datetime

# 1. Fetch VIXCLS data from FRED
start_date = "2020-01-01"
end_date = "2026-06-25"
vix = web.DataReader("VIXCLS", "fred", start_date, end_date)

# 2. Define your OOS dates (Replace this list with your specific contender's OOS dates)
# Example: oos_dates = [datetime.datetime(2026, 1, 5), ...]
oos_dates = pd.to_datetime([...]) 

# 3. Align OOS dates with VIX data
oos_data = vix.loc[vix.index.isin(oos_dates)]

# 4. Compute Clustering
total_oos = len(oos_data)
high_vix_oos = oos_data[oos_data['VIXCLS'] >= 18]
low_vix_oos = oos_data[oos_data['VIXCLS'] < 18]

# 5. Compare against the full sample distribution (The "Expected" distribution)
total_vix = len(vix)
high_vix_total = vix[vix['VIXCLS'] >= 18]
low_vix_total = vix[vix['VIXCLS'] < 18]

expected_ratio = len(high_vix_total) / total_vix

print(f"--- OOS Clustering Analysis ---")
print(f"Total OOS Days: {total_oos}")
print(f"Days in VIX < 18: {len(low_vix_oos)} ({len(low_vix_oos)/total_oos:.1%})")
print(f"Days in VIX >= 18: {len(high_vix_oos)} ({len(high_vix_oos)/total_oos:.1%})")

# 6. Statistical Significance (Chi-Square)
# Null Hypothesis: OOS days are distributed randomly relative to the VIX regime
observed = [len(high_vix_oos), len(low_vix_oos)]
expected = [total_oos * expected_ratio, total_oos * (1 - expected_ratio)]

chi2, p_value = chisquare(f_obs=observed, f_exp=expected)

print(f"\nChi-Square p-value: {p_value:.4f}")
if p_value < 0.05:
    print("Result: Significant clustering detected.")
else:
    print("Result: No significant clustering detected (random distribution).")
```

### How to interpret the results:

1.  **The Regime Split:** The code calculates the percentage of your OOS days that fall into the "High Volatility" regime ($VIX \ge 18$).
2.  **The Statistical Test:** The `chisquare` test compares your OOS distribution against the historical frequency of the VIX regimes from 2020 to today. 
    *   If the **p-value < 0.05**, it suggests that your contender's OOS performance is not randomly distributed across volatility regimes. 
    *   If your contender has a high percentage of OOS days in the $VIX \ge 18$ bucket, it indicates a **"Volatility Bias,"** meaning the model is either struggling or being tested disproportionately during market stress.
3.  **Data Integrity:** Since today is **2026-06-25**, the FRED API will provide the most current market data available. Ensure your `oos_dates` list is formatted as a list of `datetime` objects to ensure accurate matching with the FRED index.

**Would you like me to adjust the threshold or include a rolling-window volatility analysis?**