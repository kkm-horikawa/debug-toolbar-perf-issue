import uuid

from django.db import models


class Item(models.Model):
    """Simple model with UUID primary key to reproduce the issue."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
