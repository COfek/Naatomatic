"""Repository layer — transactional read/write access to the DB.

One repository per aggregate (personnel, network, logistics, scheduling). Tools and
the Validator go through here; nothing else writes the database directly.
Planned: personnel_repo.py, network_repo.py, logistics_repo.py, scheduling_repo.py.
"""
