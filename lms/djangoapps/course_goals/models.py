"""
Course Goals Models
"""


from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import ugettext_lazy as _
from model_utils import Choices
from opaque_keys.edx.django.models import CourseKeyField
from simple_history.models import HistoricalRecords

# Each goal is represented by a goal key and a string description.
GOAL_KEY_CHOICES = Choices(
    ('certify', _('Earn a certificate')),
    ('complete', _('Complete the course')),
    ('explore', _('Explore the course')),
    ('unsure', _('Not sure yet')),
)

User = get_user_model()


class CourseGoal(models.Model):
    """
    Represents a course goal set by a user on the course home page.

    .. no_pii:
    """
    class Meta:
        app_label = 'course_goals'
        unique_together = ('user', 'course_key')

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course_key = CourseKeyField(max_length=255, db_index=True)
    # The goal a user has set for the number of days they want to learn per week
    days_per_week = models.PositiveIntegerField(default=0)
    # Controls whether a user will receive emails reminding them to stay on track with their learning goal
    subscribed_to_reminders = models.BooleanField(default=False)
    goal_key = models.CharField(max_length=100, choices=GOAL_KEY_CHOICES, default=GOAL_KEY_CHOICES.unsure)
    history = HistoricalRecords()

    def __str__(self):
        return 'CourseGoal: {user} set goal to {goal} days per week for course {course}'.format(
            user=self.user.username,
            goal=self.days_per_week,
            course=self.course_key,
        )


class UserActivity(models.Model):
    """
    Tracks the date a user performs an activity in a course for goal purposes.
    To be used in conjunction with the CourseGoal model to establish if a learner is hitting
    their desired days_per_week.

    To start, this model will only be tracking page views that count towards a learner's goal,
    but could grow to tracking other types of goal achieving activities in the future.

    .. no_pii:
    """
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'course_key', 'date'], name='unique_user_course_date')]
        indexes = [models.Index(fields=['user', 'course_key'], name='user_course_index')]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course_key = CourseKeyField(max_length=255)
    date = models.DateField()
