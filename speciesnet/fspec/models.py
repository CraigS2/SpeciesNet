from django.db import models

# Create your models here.

class FSpec (models.Model):
    name = models.CharField (max_length=200)
    description = models.TextField(null=True, blank=True)  # allows empty text or form
    lastUpdated = models.DateTimeField(auto_now=True)      # updated every DB FSpec save
    created = models.DateTimeField(auto_now_add=True)      # updated only at 1st save

    def __str__(self):
        return self.name