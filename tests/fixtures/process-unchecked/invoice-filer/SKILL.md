---
name: invoice-filer
description: Files a supplier invoice into the month's folder and adds it to the payables list. Use when an invoice PDF arrives, when the user asks to file or log an invoice, or when the payables list is missing an invoice that is already on disk.
---

# Invoice filer

1. Read the supplier, the amount and the due date off the invoice.
2. Check `payables.csv` for the same invoice number before adding anything, and stop
   if it is already there.
3. Move the PDF into the folder for the month of the due date.
4. Append one row to `payables.csv` and print it.
