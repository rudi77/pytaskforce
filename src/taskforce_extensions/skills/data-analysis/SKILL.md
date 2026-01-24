---
name: data-analysis
description: Analyze data, create visualizations, and extract insights. Use when the user wants to analyze datasets, create charts, perform statistical analysis, or understand data patterns.
---

# Data Analysis Skill

This skill provides comprehensive data analysis capabilities including:
- Exploratory data analysis (EDA)
- Statistical analysis
- Data visualization
- Pattern recognition
- Report generation

## Analysis Workflow

### 1. Data Understanding

Start by understanding the data:
- What is the data source?
- What are the columns/features?
- What is the data type of each column?
- What is the size of the dataset?

```python
import pandas as pd

# Load and inspect data
df = pd.read_csv('data.csv')
print(df.info())
print(df.describe())
print(df.head())
```

### 2. Data Quality Assessment

Check for data quality issues:
- Missing values
- Duplicate records
- Outliers
- Inconsistent formatting

```python
# Check missing values
print(df.isnull().sum())

# Check duplicates
print(f"Duplicates: {df.duplicated().sum()}")

# Check for outliers using IQR
Q1 = df.quantile(0.25)
Q3 = df.quantile(0.75)
IQR = Q3 - Q1
outliers = ((df < (Q1 - 1.5 * IQR)) | (df > (Q3 + 1.5 * IQR))).sum()
print(f"Outliers per column:\n{outliers}")
```

### 3. Exploratory Analysis

Explore relationships in the data:
- Univariate analysis
- Bivariate analysis
- Correlation analysis

```python
import matplotlib.pyplot as plt
import seaborn as sns

# Distribution plots
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
df['column'].hist(ax=axes[0])
axes[0].set_title('Distribution')
sns.boxplot(data=df, y='column', ax=axes[1])
axes[1].set_title('Box Plot')
plt.tight_layout()
plt.savefig('distribution.png')

# Correlation matrix
correlation = df.corr()
plt.figure(figsize=(10, 8))
sns.heatmap(correlation, annot=True, cmap='coolwarm')
plt.savefig('correlation.png')
```

### 4. Statistical Analysis

Perform statistical tests:
- Descriptive statistics
- Hypothesis testing
- Confidence intervals

```python
from scipy import stats

# T-test example
group1 = df[df['group'] == 'A']['value']
group2 = df[df['group'] == 'B']['value']
t_stat, p_value = stats.ttest_ind(group1, group2)
print(f"T-statistic: {t_stat}, P-value: {p_value}")

# Chi-square test for categorical data
contingency = pd.crosstab(df['cat1'], df['cat2'])
chi2, p, dof, expected = stats.chi2_contingency(contingency)
print(f"Chi-square: {chi2}, P-value: {p}")
```

### 5. Insights and Reporting

Summarize findings clearly:

```markdown
## Analysis Report

### Key Findings
1. [Primary finding with supporting data]
2. [Secondary finding]
3. [Additional observations]

### Visualizations
[Include relevant charts]

### Recommendations
[Actionable recommendations based on analysis]

### Limitations
[Note any data quality issues or analysis limitations]
```

## Best Practices

- Always validate data before analysis
- Document assumptions and limitations
- Use appropriate statistical methods
- Create clear, labeled visualizations
- Provide actionable insights
