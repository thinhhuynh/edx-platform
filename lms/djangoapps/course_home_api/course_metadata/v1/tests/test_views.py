"""
Tests for the Course Home Course Metadata API in the Course Home API
"""

import ddt
import mock
from django.urls import reverse

from edx_toggles.toggles.testutils import override_waffle_flag
from common.djangoapps.course_modes.models import CourseMode
from common.djangoapps.student.roles import CourseInstructorRole
from lms.djangoapps.courseware.toggles import (
    COURSEWARE_MICROFRONTEND_PROGRESS_MILESTONES,
    COURSEWARE_MICROFRONTEND_PROGRESS_MILESTONES_STREAK_CELEBRATION,
)
from common.djangoapps.student.models import CourseEnrollment
from common.djangoapps.student.tests.factories import UserFactory
from lms.djangoapps.course_home_api.tests.utils import BaseCourseHomeTests
from lms.djangoapps.experiments.testutils import override_experiment_waffle_flag
from lms.djangoapps.experiments.utils import STREAK_DISCOUNT_EXPERIMENT_FLAG


@ddt.ddt
@override_waffle_flag(COURSEWARE_MICROFRONTEND_PROGRESS_MILESTONES, active=True)
@override_waffle_flag(COURSEWARE_MICROFRONTEND_PROGRESS_MILESTONES_STREAK_CELEBRATION, active=True)
class CourseHomeMetadataTests(BaseCourseHomeTests):
    """
    Tests for the Course Home Course Metadata API
    """
    def setUp(self):
        super().setUp()
        self.url = reverse('course-home-course-metadata', args=[self.course.id])
        self.staff_user = UserFactory(
            username='staff',
            email='staff@example.com',
            password='bar',
            is_staff=True
        )

    def test_get_authenticated_user(self):
        CourseEnrollment.enroll(self.user, self.course.id, CourseMode.VERIFIED)
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert not response.data.get('is_staff')
        # 'Course', 'Wiki', 'Progress' tabs
        assert len(response.data.get('tabs', [])) == 4

    @ddt.data(True, False)
    def test_get_authenticated_not_enrolled(self, has_previously_enrolled):
        if has_previously_enrolled:
            # Create an enrollment, then unenroll to set is_active to False
            CourseEnrollment.enroll(self.user, self.course.id)
            CourseEnrollment.unenroll(self.user, self.course.id)
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.data['is_enrolled'] is False

    def test_get_authenticated_staff_user(self):
        self.client.logout()
        self.client.login(username=self.staff_user.username, password='bar')
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.data['is_staff']
        # This differs for a staff user because they also receive the Instructor tab
        # 'Course', 'Wiki', 'Progress', and 'Instructor' tabs
        assert len(response.data.get('tabs', [])) == 5

    def test_get_masqueraded_user(self):
        CourseEnrollment.enroll(self.user, self.course.id, CourseMode.VERIFIED)

        self.client.logout()
        self.client.login(username=self.staff_user.username, password='bar')

        # Sanity check on our normal staff user
        assert self.client.get(self.url).data['username'] == self.staff_user.username

        # Now switch users and confirm we get a different result
        self.update_masquerade(username=self.user.username)
        assert self.client.get(self.url).data['username'] == self.user.username

    def test_get_unknown_course(self):
        url = reverse('course-home-course-metadata', args=['course-v1:unknown+course+2T2020'])
        response = self.client.get(url)
        assert response.status_code == 404

    def test_streak_data_in_response(self):
        """ Test that metadata endpoint returns data for the streak celebration """
        CourseEnrollment.enroll(self.user, self.course.id, 'audit')
        with override_experiment_waffle_flag(STREAK_DISCOUNT_EXPERIMENT_FLAG, active=True):
            with mock.patch('common.djangoapps.student.models.UserCelebration.perform_streak_updates', return_value=3):
                response = self.client.get(self.url, content_type='application/json')
                celebrations = response.json()['celebrations']
                assert celebrations['streak_length_to_celebrate'] == 3
                assert celebrations['streak_discount_experiment_enabled'] is True

    @ddt.data(
        # Who has access to MFE courseware?
        {
            # Enrolled learners should have access.
            'enroll_user': True,
            'instructor_role': False,
            'masquerade_role': None,
            'expect_course_access': True,
        },
        {
            # Un-enrolled learners should NOT have access.
            'enroll_user': False,
            'instructor_role': False,
            'masquerade_role': None,
            'expect_course_access': False,
        },
        {
            # Un-enrolled instructors should have access.
            'enroll_user': False,
            'instructor_role': True,
            'masquerade_role': None,
            'expect_course_access': True,
        },
        {
            # Un-enrolled instructors masquerading as students should have access.
            'enroll_user': False,
            'instructor_role': True,
            'masquerade_role': 'student',
            'expect_course_access': True,
        },
    )
    @ddt.unpack
    def test_course_access(self, enroll_user, instructor_role, masquerade_role, expect_course_access):
        """
        Test that course_access is calculated correctly based on
        access to MFE and access to the course itself.
        """
        if enroll_user:
            CourseEnrollment.enroll(self.user, self.course.id, 'audit')
        if instructor_role:
            CourseInstructorRole(self.course.id).add_users(self.user)
        if masquerade_role:
            self.update_masquerade(role=masquerade_role)

        response = self.client.get(self.url)

        assert response.status_code == 200
        if expect_course_access:
            assert response.data['course_access']['has_access']
        else:
            assert not response.data['course_access']['has_access']

        # Start date is used when handling some errors, so make sure it is present too
        assert response.data['start'] == self.course.start.isoformat() + 'Z'
