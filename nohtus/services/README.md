# nohtus.services

Business logic should move here before moving page functions.

Suggested modules:

- products.py: product master, ERP mapping, aliases
- inventory.py: add/move/adjust inventory, transaction logs
- outbound.py: outbound orders and picking output
- history.py: transaction history queries and pagination helpers
- closing.py: closing checks and ERP stock comparison

Keep functions independent from Streamlit whenever possible.
