# Scraper keyword config

Used by every scraper. Tier-1 = hard match; tier-2 = fit-score boost only.

## Tier 1 (hard match)

```
business analyst
senior business analyst
sr business analyst
sr BA
lead business analyst
business analysis consultant
product analyst
senior product analyst
product owner
senior product owner
insurance business analyst
BFSI business analyst
banking business analyst
compliance analyst
senior compliance analyst
regulatory analyst
management consultant
consultant business analysis
business systems analyst
```

## Tier 2 (transferable, scored)

```
process analyst
process improvement consultant
business process analyst
data analyst (stakeholder focus)
digital transformation analyst
operations analyst BFSI
operations manager BFSI
policy analyst insurance
risk analyst insurance
risk analyst credit
claims analyst lead
claims operations manager
underwriting analyst lead
underwriting operations
KYC analyst senior
AML analyst senior
scrum master BA
agile coach BA
business transformation consultant
solution analyst BFSI
```

## Exclude (negative regex, case-insensitive)

```
intern | fresher | trainee | junior | jr\.? | entry[\s-]level
0-2\s*yr | 1-3\s*yr | 0\s*to\s*2 | 1\s*to\s*3
software (developer|engineer) | full[\s-]stack | backend | frontend | devops
(?<!engineering manager )ml engineer | data engineer | qa engineer | sde
```

## Location filter

```
delhi | new delhi | gurgaon | gurugram | noida | greater noida | faridabad | ghaziabad
NCR | national capital region
remote | work from home | wfh | hybrid india
```

## Experience filter

```
5-12 yr
4+ yr (with senior in title)
6+ yr
8+ yr (lead/principal roles)
```

Avoid: anything specifying "10+ yr only" if salary < ₹22 LPA (rare but happens — score down).
