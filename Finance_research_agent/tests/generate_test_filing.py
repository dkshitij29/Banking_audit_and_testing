"""Generate a fake 10-K PDF for testing the upload + research pipeline."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch

SECTIONS = [
    ("UNITED STATES SECURITIES AND EXCHANGE COMMISSION", [
        "Securities and Exchange Commission",
        "Washington, D.C. 20549",
        "",
        "FORM 10-K",
        "",
        "For the fiscal year ended September 28, 2025",
        "",
        "ACME TECHNOLOGIES INC.",
        "(Exact name of registrant as specified in its charter)",
        "",
        "Ticker Symbol: ACME",
        "Commission File Number: 001-39821",
    ]),
    ("ITEM 1. BUSINESS", [
        "Acme Technologies Inc. (the 'Company' or 'Acme') is a leading provider of cloud-based enterprise software solutions.",
        "The Company was founded in 2015 and is headquartered in San Francisco, California.",
        "",
        "Our products serve over 10,000 enterprise customers across North America, Europe and Asia-Pacific.",
        "Revenue is derived primarily from software subscriptions, professional services, and maintenance contracts.",
        "The Company operates in two segments: Cloud Platform (72% of revenue) and Enterprise Applications (28% of revenue).",
    ]),
    ("ITEM 1A. RISK FACTORS", [
        "Our business is subject to significant risks including:",
        "",
        "1. Competition: The cloud software market is highly competitive. We compete with large incumbents such as Salesforce, Oracle, and Microsoft who have greater financial resources.",
        "",
        "2. Customer Concentration: Our top 10 customers accounted for 34% of total revenue in fiscal 2025. Loss of any major customer could materially impact our results.",
        "",
        "3. Cybersecurity: A significant data breach could damage our reputation and result in substantial liability. We invest over $15M annually in security infrastructure.",
        "",
        "4. Regulatory Risk: Evolving data privacy regulations (GDPR, CCPA) increase compliance costs and may limit how we process customer data.",
        "",
        "5. Economic Sensitivity: A recession could cause customers to defer or cancel subscriptions, reducing our recurring revenue.",
    ]),
    ("ITEM 1B. UNRESOLVED STAFF COMMENTS", [
        "None.",
    ]),
    ("ITEM 2. PROPERTIES", [
        "Our headquarters occupies approximately 85,000 square feet at 100 Market Street, San Francisco, CA.",
        "We also maintain development centers in Austin, TX (40,000 sq ft) and Seattle, WA (30,000 sq ft).",
        "All properties are leased with an average remaining term of 6.5 years.",
    ]),
    ("ITEM 3. LEGAL PROCEEDINGS", [
        "In March 2024, the Company was named as a defendant in a patent infringement lawsuit filed by TechCorp LLC.",
        "TechCorp alleges that our Cloud Platform infringes three patents related to data compression algorithms.",
        "We believe we have strong defenses and are actively defending the action. No damages amount has been requested.",
        "We do not expect the outcome of this matter to have a material adverse effect on our business.",
    ]),
    ("ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS", [
        "Overview:",
        "Fiscal 2025 was a strong year. Total revenue grew 18.2% year-over-year to $3,847 million.",
        "Gross margin improved to 76.4% from 74.1% in fiscal 2024, driven by the favorable mix shift toward higher-margin cloud subscriptions.",
        "",
        "Revenue Analysis:",
        "Cloud Platform revenue grew 24.1% to $2,770 million, driven by new customer acquisitions and strong expansion within the existing base.",
        "Enterprise Applications revenue grew 8.3% to $1,077 million, with legacy on-premise contracts transitioning to cloud.",
        "",
        "Operating Expenses:",
        "R&D expense increased 12% to $620 million (16.1% of revenue), reflecting continued investment in our next-generation platform.",
        "Sales and Marketing expense increased 15% to $960 million (25.0% of revenue), primarily from headcount growth.",
        "General and Administrative expense was flat at $210 million (5.5% of revenue).",
        "",
        "Liquidity:",
        "We ended the year with $2,100 million in cash and equivalents. Net debt stands at $1,850 million.",
        "Operating cash flow was $920 million, free cash flow was $780 million.",
    ]),
    ("ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK", [
        "Interest Rate Risk: We have $2,400 million in outstanding debt, of which $1,200 million is variable-rate. A 100bps increase in rates would increase annual interest expense by approximately $12 million.",
        "",
        "Foreign Exchange Risk: Approximately 28% of revenue is denominated in non-USD currencies. We use forward contracts to hedge approximately 60% of forecasted foreign currency exposures.",
    ]),
    ("ITEM 8. FINANCIAL STATEMENTS", [
        "CONSOLIDATED STATEMENTS OF INCOME",
        "(in millions, except per share data)",
        "",
        "Fiscal Year Ended Sept 28:",
        "                              2025       2024       2023",
        "Revenue                    $3,847     $3,254     $2,780",
        "Cost of revenue             913        847        701",
        "Gross profit               2,934      2,407      2,079",
        "",
        "Operating expenses:",
        "  R&D                        620        553        468",
        "  Sales & marketing          960        834        712",
        "  General & admin            210        201        187",
        "Total operating expenses   1,790      1,588      1,367",
        "",
        "Operating income           1,144        819        712",
        "Interest expense             (58)       (52)       (48)",
        "Other income, net             12         18         10",
        "Income before tax          1,098        785        674",
        "Income tax expense          (231)      (165)      (142)",
        "Net income                 $ 867      $ 620      $ 532",
        "",
        "EPS - basic              $  2.89    $  2.08    $  1.78",
        "EPS - diluted            $  2.84    $  2.04    $  1.74",
        "Shares outstanding (mm)    300.1      298.0      298.9",
        "",
        "CONSOLIDATED BALANCE SHEET (key items)",
        "(in millions)",
        "",
        "As of Sept 28:",
        "                          2025         2024",
        "Cash and equivalents     $2,100       $1,680",
        "Accounts receivable       1,150        1,020",
        "Total current assets      3,400        2,950",
        "Property & equipment        480          420",
        "Goodwill                   1,200        1,180",
        "Total assets              5,650        4,980",
        "",
        "Short-term debt            300          200",
        "Accounts payable           420          380",
        "Total current liab.      1,800        1,560",
        "Long-term debt           2,100        1,950",
        "Total liabilities        4,150        3,680",
        "Total equity             1,500        1,300",
        "",
        "CONSOLIDATED CASH FLOW (key items)",
        "(in millions)",
        "",
        "Fiscal Year Ended Sept 28:",
        "                              2025       2024       2023",
        "Operating cash flow          $ 920      $ 750      $ 620",
        "Capital expenditures          (140)      (120)      (105)",
        "Free cash flow                780        630        515",
    ]),
    ("ITEM 9A. CONTROLS AND PROCEDURES", [
        "The Company's Chief Executive Officer and Chief Financial Officer have concluded that the Company's disclosure controls and procedures were effective as of September 28, 2025.",
        "There were no changes in internal control over financial reporting during the fourth quarter of fiscal 2025 that materially affected, or are reasonably likely to materially affect, our internal control.",
    ]),
    ("ITEM 15. EXHIBITS AND FINANCIAL STATEMENT SCHEDULES", [
        "Exhibit 31.1 - Certification of CEO pursuant to Section 302 of the Sarbanes-Oxley Act",
        "Exhibit 31.2 - Certification of CFO pursuant to Section 302 of the Sarbanes-Oxley Act",
        "Exhibit 32.1 - Certification pursuant to 18 U.S.C. Section 1350",
    ]),
    ("SIGNATURES", [
        "Pursuant to the requirements of the Securities Exchange Act of 1934, the registrant has duly caused this report to be signed on its behalf by the undersigned hereunto duly authorized.",
        "",
        "ACME TECHNOLOGIES INC.",
        "",
        "By: /s/ Jane Roberts",
        "    Jane Roberts",
        "    Chief Financial Officer",
        "",
        "Date: November 15, 2025",
    ]),
]


def build_pdf(output_path: str):
    doc = SimpleDocTemplate(output_path, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle("SectionHeading", parent=styles["Heading1"], fontSize=14, spaceBefore=24, spaceAfter=6, textColor="#1a1a1a")
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=16, spaceAfter=4, textColor="#1a1a1a")
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14, spaceBefore=2)

    flow = []
    for heading, lines in SECTIONS:
        flow.append(Paragraph(heading, title_style if "FORM 10-K" not in lines[0] and len(heading) < 40 else heading_style))
        flow.append(Spacer(1, 6))
        for line in lines:
            flow.append(Paragraph(line if line else "<br/>", body))
        flow.append(Spacer(1, 10))

    doc.build(flow)
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "ACME_10K_2025.pdf")
    build_pdf(out)
