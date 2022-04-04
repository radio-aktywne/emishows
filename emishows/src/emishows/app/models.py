from django.db import models


class Show(models.Model):
    label = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=100)
    description = models.TextField(null=True)

    def __str__(self):
        return f"Show {self.id} ('{self.title}')"


class Event(models.Model):
    class Type(models.IntegerChoices):
        LIVE = 1
        REPLAY = 2

    id = models.UUIDField(primary_key=True)
    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    type = models.IntegerField(choices=Type.choices)

    def __str__(self):
        if self.show is None:
            return f"Event {self.id}"
        return f"Event {self.id} ('{self.show.title}')"
