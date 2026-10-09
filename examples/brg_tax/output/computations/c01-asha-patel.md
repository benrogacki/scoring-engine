# Asha Patel Consulting - Self-employment computation 2025-26

Period 2025-04-01 to 2026-03-31 (365 days) · as of 2026-10-09 · status: **Ready**

| Line | £ | Rules | Authority |
|---|---:|---|---|
| Net profit per the accounts | £72,258.00 | SA-PROFIT-01 | ITTOIA 2005 s5; ITTOIA 2005 s25 |
| Add: depreciation and amortisation | £500.00 | EXP-DEP-01 | CTA 2009 s53; ITTOIA 2005 s33 |
| Add: business entertainment of non-employees | £350.00 | EXP-ENT-01 | CTA 2009 s1298; ITTOIA 2005 s45; SI 1992/3222 art 5 |
| Add: mixed-use costs with a recorded business-use percentage | £96.00 | EXP-PRIV-01 | ITTOIA 2005 s34(2) |
| Less: annual investment allowance | (£1,500.00) | CA-AIA-01 | CAA 2001 s38A; CAA 2001 s38B; CAA 2001 s51A |
| **Taxable trading profit 2025-26** | **£71,704.00** | SA-PROFIT-01, SA-BASIS-01 | ITTOIA 2005 s5; ITTOIA 2005 s25; ITTOIA 2005 s7A; ITTOIA 2005 s209A |
| Less: personal allowance | (£12,570.00) | SA-IT-01, EXT-PA-01 | ITA 2007 s6; ITA 2007 s10; ITA 2007 s23; ITA 2007 s35 |
| **Taxable income** | **£59,134.00** | SA-IT-01 | ITA 2007 s6; ITA 2007 s10; ITA 2007 s23; ITA 2007 s35 |
| Income tax: £37,700.00 at 20% (basic rate, England) | £7,540.00 | SA-IT-01 | ITA 2007 s6; ITA 2007 s10; ITA 2007 s23; ITA 2007 s35 |
| Income tax: £21,434.00 at 40% (higher rate, England) | £8,573.60 | SA-IT-01 | ITA 2007 s6; ITA 2007 s10; ITA 2007 s23; ITA 2007 s35 |
| **Income tax** | **£16,113.60** | SA-IT-01 | ITA 2007 s6; ITA 2007 s10; ITA 2007 s23; ITA 2007 s35 |
| Class 4 NIC (6% between £12,570.00 and £50,270.00, 2% above) | £2,690.68 | SA-C4-01 | SSCBA 1992 s15 |
| Class 2 NIC: credited (no payment due) | £0.00 | SA-C2-01 | SSCBA 1992 s11; NICs (Reduction in Rates) (No. 2) Act 2024 |
| **Total income tax and NIC 2025-26** | **£18,804.28** | SA-IT-01, SA-C4-01, SA-C2-01 | ITA 2007 s6; ITA 2007 s10; ITA 2007 s23; ITA 2007 s35 |
| **Balancing payment due 31 January 2026 (after POAs paid of £15,000.00)** | £3,804.28 | SA-POA-01 | TMA 1970 s59A; SI 1996/1654 reg 3 |
| **Payments on account for 2026-27: two of £9,402.14 (31 January and 31 July 2026)** | £9,402.14 | SA-POA-01, SA-POA-02 | TMA 1970 s59A; SI 1996/1654 reg 3; TMA 1970 s59A(3) |

## Line detail

**Net profit per the accounts**
- Income £78,000.00 less expenses £5,742.00 from 43 ledger lines

**Add: depreciation and amortisation**
- 2026-03-31 Depreciation - computer equipment: £500.00

**Add: business entertainment of non-employees**
- 2025-11-14 Client lunch - project kick-off: £350.00

**Add: mixed-use costs with a recorded business-use percentage**
- 2025-04-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-05-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-06-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-07-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-08-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-09-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-10-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-11-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2025-12-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2026-01-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2026-02-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)
- 2026-03-12 Mobile and broadband: £8.00 (20% private/non-business use disallowed)

**Less: annual investment allowance**
- AIA limit for the period £1,000,000.00
- Parameter `ca.it.aia_limit` (2024-25) = 1000000 - CAA 2001 s51A - UNVERIFIED - https://www.gov.uk/capital-allowances/annual-investment-allowance
- Parameter `ca.it.aia_limit` (2025-26) = 1000000 - CAA 2001 s51A - UNVERIFIED - https://www.gov.uk/capital-allowances/annual-investment-allowance

**Less: personal allowance**
- Parameter `it.personal_allowance` (2025-26) = 12570 - ITA 2007 s35 - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-income-tax/income-tax-rates-and-allowances-current-and-past
- Parameter `it.pa_taper_threshold` (2025-26) = 100000 - ITA 2007 s35(2) - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-income-tax/income-tax-rates-and-allowances-current-and-past

**Income tax: £37,700.00 at 20% (basic rate, England)**
- Parameter `it.ruk.bands` (2025-26) = [{"upto": 37700, "rate": 20, "name": "basic"}, {"upto": 125140, "rate": 40, "name": "higher"}, {"upto": null, "rate": 45, "name": "additional"}] - ITA 2007 s6, s10; Finance Act (annual) income tax charge - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-income-tax/income-tax-rates-and-allowances-current-and-past

**Income tax: £21,434.00 at 40% (higher rate, England)**
- Parameter `it.ruk.bands` (2025-26) = [{"upto": 37700, "rate": 20, "name": "basic"}, {"upto": 125140, "rate": 40, "name": "higher"}, {"upto": null, "rate": 45, "name": "additional"}] - ITA 2007 s6, s10; Finance Act (annual) income tax charge - UNVERIFIED - https://www.gov.uk/government/publications/rates-and-allowances-income-tax/income-tax-rates-and-allowances-current-and-past

**Class 4 NIC (6% between £12,570.00 and £50,270.00, 2% above)**
- Parameter `nic.class4.lower_profits_limit` (2025-26) = 12570 - SSCBA 1992 s15(3) - UNVERIFIED - https://www.gov.uk/self-employed-national-insurance-rates
- Parameter `nic.class4.upper_profits_limit` (2025-26) = 50270 - SSCBA 1992 s15(3) - UNVERIFIED - https://www.gov.uk/self-employed-national-insurance-rates
- Parameter `nic.class4.main_rate` (2025-26) = 6 - SSCBA 1992 s15(3ZA) - UNVERIFIED - https://www.gov.uk/self-employed-national-insurance-rates
- Parameter `nic.class4.additional_rate` (2025-26) = 2 - SSCBA 1992 s15(3ZA)(b) - UNVERIFIED - https://www.gov.uk/self-employed-national-insurance-rates

**Class 2 NIC: credited (no payment due)**
- Parameter `nic.class2.compulsory` (2025-26) = false - SSCBA 1992 s11 as amended by NICs (Reduction in Rates) (No. 2) Act 2024 - UNVERIFIED - https://www.gov.uk/self-employed-national-insurance-rates
- Parameter `nic.class2.weekly_rate` (2025-26) = 3.5 - SSCBA 1992 s11(1) - UNVERIFIED - https://www.gov.uk/self-employed-national-insurance-rates
- Parameter `nic.class2.small_profits_threshold` (2025-26) = 6845 - SSCBA 1992 s11(4) - UNVERIFIED - https://www.gov.uk/self-employed-national-insurance-rates

**Payments on account for 2026-27: two of £9,402.14 (31 January and 31 July 2026)**
- Parameter `sa.poa_threshold` (2025-26) = 1000 - SI 1996/1654 reg 3 - UNVERIFIED - https://www.gov.uk/understand-self-assessment-bill/payments-on-account
- Parameter `sa.poa_at_source_pct` (2025-26) = 80 - SI 1996/1654 reg 3 - UNVERIFIED - https://www.gov.uk/understand-self-assessment-bill/payments-on-account

## Capital allowances

| Allowance | £ | Rules |
|---|---:|---|
| Annual investment allowance | £1,500.00 | CA-AIA-01 |

Pools carried forward: main £0.00, special £0.00

## Sole trader vs limited company (illustrative, SA-INC-01)

At a profit of £71,704.00: sole trader tax £18,804.28, net £52,899.72; company route total tax and admin £47,192.60 (salary £100,000.00), net £68,557.40. Difference £15,657.68.

MTD for Income Tax: mandated from 2027-28; software recorded: no.

## Alerts

- **warning** (SA-MTD-01): Will be within MTD for Income Tax from 2027-28 (qualifying income above the threshold).
- **warning** (VAT-REG-01): Rolling 12-month taxable turnover £84,000.00 is 93% of the £90,000.00 threshold (headroom £6,000.00). Monitor monthly; registration is needed at the end of any month the total exceeds the threshold.

## Data health

- OK Trial balance balances: Debits £82,000.00, credits £82,000.00
- OK Ledger profit agrees to the trial balance: TB profit £72,258.00, ledger £72,258.00
- OK No uncategorised transactions: All transactions map to a BRG category
- OK Fixed asset register agrees to the ledger: Register additions £1,500.00, ledger fixed asset postings £1,500.00
- WARN Parameters exist and are verified: Years 2024-25, 2025-26, 2026-27: 0 of 274 values verified against GOV.UK - run `brg-tax params-update`

_Outputs are working papers to support professional review and are not advice until reviewed and signed off. Synthetic sample clients contain no real data._
