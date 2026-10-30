"""Bounded historical-text adapter over the actual SE6 Entity memory store."""
def __getattr__(name):
    # The conventional arm shares only the pure source formatter. Importing it
    # must not initialize SE6 or charge its dependencies to control startup.
    if name == 'Memory':
        from .adapter import Memory
        return Memory
    raise AttributeError(name)

__all__=['Memory']
