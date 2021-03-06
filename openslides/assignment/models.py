from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy, ugettext_noop

from openslides.agenda.models import Item, Speaker
from openslides.core.models import Tag
from openslides.config.api import config
from openslides.poll.models import (BaseOption, BasePoll, BaseVote,
                                    CollectDefaultVotesMixin,
                                    PublishPollMixin)
from openslides.projector.models import SlideMixin
from openslides.utils.exceptions import OpenSlidesError
from openslides.utils.models import AbsoluteUrlMixin
from openslides.utils.rest_api import RESTModelMixin
from openslides.utils.utils import html_strong
from openslides.users.models import User


class AssignmentCandidate(RESTModelMixin, models.Model):
    """
    Many2Many table between an assignment and the candidates.
    """
    assignment = models.ForeignKey("Assignment")
    person = models.ForeignKey(User, db_index=True)
    elected = models.BooleanField(default=False)
    blocked = models.BooleanField(default=False)

    class Meta:
        unique_together = ("assignment", "person")

    def __str__(self):
        return str(self.person)

    def get_root_rest_element(self):
        """
        Returns the assignment to this instance which is the root REST element.
        """
        return self.assignment


class Assignment(RESTModelMixin, SlideMixin, AbsoluteUrlMixin, models.Model):
    slide_callback_name = 'assignment'

    STATUS = (
        ('sea', ugettext_lazy('Searching for candidates')),
        ('vot', ugettext_lazy('Voting')),
        ('fin', ugettext_lazy('Finished')),
    )

    name = models.CharField(max_length=100, verbose_name=ugettext_lazy("Name"))
    description = models.TextField(null=True, blank=True, verbose_name=ugettext_lazy("Description"))
    posts = models.PositiveSmallIntegerField(verbose_name=ugettext_lazy("Number of available posts"))
    poll_description_default = models.CharField(
        max_length=79, null=True, blank=True,
        verbose_name=ugettext_lazy("Default comment on the ballot paper"))
    status = models.CharField(max_length=3, choices=STATUS, default='sea')
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        permissions = (
            ('can_see_assignment', ugettext_noop('Can see elections')),  # TODO: Add plural s to the codestring
            ('can_nominate_other', ugettext_noop('Can nominate another person')),
            ('can_nominate_self', ugettext_noop('Can nominate oneself')),
            ('can_manage_assignment', ugettext_noop('Can manage elections')),  # TODO: Add plural s also to the codestring
        )
        ordering = ('name',)
        verbose_name = ugettext_noop('Election')

    def __str__(self):
        return self.name

    def get_absolute_url(self, link='detail'):
        if link == 'detail':
            url = reverse('assignment_detail', args=[str(self.pk)])
        elif link == 'update':
            url = reverse('assignment_update', args=[str(self.pk)])
        elif link == 'delete':
            url = reverse('assignment_delete', args=[str(self.pk)])
        else:
            url = super(Assignment, self).get_absolute_url(link)
        return url

    def get_slide_context(self, **context):
        context.update({
            'polls': self.poll_set.filter(published=True),
            'vote_results': self.vote_results(only_published=True)})
        return super(Assignment, self).get_slide_context(**context)

    def set_status(self, status):
        status_dict = dict(self.STATUS)
        if status not in status_dict:
            raise ValueError(_('%s is not a valid status.') % html_strong(status))
        if self.status == status:
            raise ValueError(
                _('The election status is already %s.') % html_strong(status_dict[status]))
        self.status = status
        self.save()

    def run(self, candidate, person=None):
        """
        run for a vote
        candidate: The user who will be a candidate
        person: The user who chooses the candidate
        """
        # TODO: don't make any permission checks here.
        #       Use other Exceptions
        if self.is_candidate(candidate):
            raise NameError(_('<b>%s</b> is already a candidate.') % candidate)
        if not person.has_perm("assignment.can_manage_assignment") and self.status != 'sea':
            raise NameError(_('The candidate list is already closed.'))
        candidature = self.assignment_candidates.filter(person=candidate)
        if candidature and candidate != person and \
                not person.has_perm("assignment.can_manage_assignment"):
            # if the candidature is blocked and anotherone tries to run the
            # candidate
            raise NameError(
                _('%s does not want to be a candidate.') % candidate)
        elif candidature:
            candidature[0].blocked = False
            candidature[0].save()
        else:
            AssignmentCandidate(assignment=self, person=candidate).save()

    def delrun(self, candidate, blocked=True):
        """
        stop running for a vote
        """
        try:
            candidature = self.assignment_candidates.get(person=candidate)
        except AssignmentCandidate.DoesNotExist:
            raise Exception(_('%s is no candidate') % candidate)

        if not candidature.blocked:
            if blocked:
                candidature.blocked = True
                candidature.save()
            else:
                candidature.delete()
        else:
            candidature.delete()

    def is_candidate(self, person):
        """
        return True, if person is a candidate.
        """
        try:
            return self.assignment_candidates.filter(person=person).exclude(blocked=True).exists()
        except AttributeError:
            return False

    def is_blocked(self, person):
        """
        return True, if the person is blockt for candidature.
        """
        return self.assignment_candidates.filter(person=person).filter(blocked=True).exists()

    @property
    def assignment_candidates(self):
        return AssignmentCandidate.objects.filter(assignment=self)

    @property
    def candidates(self):
        return self.get_participants(only_candidate=True)

    @property
    def elected(self):
        return self.get_participants(only_elected=True)

    def get_participants(self, only_elected=False, only_candidate=False):
        candidates = self.assignment_candidates.exclude(blocked=True)

        assert not (only_elected and only_candidate)

        if only_elected:
            candidates = candidates.filter(elected=True)

        if only_candidate:
            candidates = candidates.filter(elected=False)

        # TODO: rewrite this with a queryset
        participants = []
        for candidate in candidates.all():
            participants.append(candidate.person)
        return participants

    def set_elected(self, person, value=True):
        candidate = self.assignment_candidates.get(person=person)
        candidate.elected = value
        candidate.save()

    def is_elected(self, person):
        return person in self.elected

    def gen_poll(self):
        """
        Creates an new poll for the assignment and adds all candidates to all
        lists of speakers of related agenda items.
        """
        if config['assignment_poll_vote_values'] == 'votes':
            yesnoabstain = False
        elif config['assignment_poll_vote_values'] == 'yesnoabstain':
            yesnoabstain = True
        else:
            # config['assignment_poll_vote_values'] == 'auto'
            # candidates <= available posts -> yes/no/abstain
            if len(self.candidates) <= (self.posts - len(self.elected)):
                yesnoabstain = True
            else:
                yesnoabstain = False

        poll = AssignmentPoll.objects.create(
            assignment=self,
            description=self.poll_description_default,
            yesnoabstain=yesnoabstain)
        poll.set_options([{'candidate': person} for person in self.candidates])

        items = Item.objects.filter(content_type=ContentType.objects.get_for_model(Assignment), object_id=self.pk)
        for item in items:
            for candidate in self.candidates:
                try:
                    Speaker.objects.add(candidate, item)
                except OpenSlidesError:
                    # The Speaker is already on the list. Do nothing.
                    # TODO: Find a smart way not to catch the error concerning AnonymousUser.
                    pass

        return poll

    def vote_results(self, only_published):
        """
        returns a table represented as a list with all candidates from all
        related polls and their vote results.
        """
        vote_results_dict = SortedDict()
        # All polls related to this assigment
        polls = self.poll_set.all()
        if only_published:
            polls = polls.filter(published=True)
        # All PollOption-Objects related to this assignment
        options = []
        for poll in polls:
            options += poll.get_options()

        for option in options:
            candidate = option.candidate
            if candidate in vote_results_dict:
                continue
            vote_results_dict[candidate] = []
            for poll in polls:
                votes = {}
                try:
                    # candidate related to this poll
                    poll_option = poll.get_options().get(candidate=candidate)
                    for vote in poll_option.get_votes():
                        votes[vote.value] = vote.print_weight()
                except AssignmentOption.DoesNotExist:
                    # candidate not in related to this poll
                    votes = None
                vote_results_dict[candidate].append(votes)
        return vote_results_dict

    def get_agenda_title(self):
        return self.name

    def get_agenda_title_supplement(self):
        return '(%s)' % _('Assignment')


class AssignmentVote(RESTModelMixin, BaseVote):
    option = models.ForeignKey('AssignmentOption')

    def get_root_rest_element(self):
        """
        Returns the assignment to this instance which is the root REST element.
        """
        return self.option.poll.assignment


class AssignmentOption(RESTModelMixin, BaseOption):
    poll = models.ForeignKey('AssignmentPoll')
    candidate = models.ForeignKey(User)
    vote_class = AssignmentVote

    def __str__(self):
        return str(self.candidate)

    def get_root_rest_element(self):
        """
        Returns the assignment to this instance which is the root REST element.
        """
        return self.poll.assignment


class AssignmentPoll(RESTModelMixin, SlideMixin, CollectDefaultVotesMixin,
                     PublishPollMixin, AbsoluteUrlMixin, BasePoll):

    slide_callback_name = 'assignmentpoll'
    """Name of the callback for the slide system."""

    option_class = AssignmentOption
    assignment = models.ForeignKey(Assignment, related_name='poll_set')
    yesnoabstain = models.BooleanField(default=False)
    description = models.CharField(
        max_length=79, null=True, blank=True,
        verbose_name=ugettext_lazy("Comment on the ballot paper"))

    def __str__(self):
        return _("Ballot %d") % self.get_ballot()

    def get_absolute_url(self, link='update'):
        """
        Return an URL for the poll.

        The keyargument 'link' can be 'update' or 'delete'.
        """
        if link == 'update':
            url = reverse('assignmentpoll_update', args=[str(self.pk)])
        elif link == 'delete':
            url = reverse('assignmentpoll_delete', args=[str(self.pk)])
        else:
            url = super(AssignmentPoll, self).get_absolute_url(link)
        return url

    def get_assignment(self):
        return self.assignment

    def get_vote_values(self):
        if self.yesnoabstain:
            return [ugettext_noop('Yes'), ugettext_noop('No'), ugettext_noop('Abstain')]
        else:
            return [ugettext_noop('Votes')]

    def get_ballot(self):
        return self.assignment.poll_set.filter(id__lte=self.id).count()

    def get_percent_base_choice(self):
        return config['assignment_poll_100_percent_base']

    def append_pollform_fields(self, fields):
        fields.append('description')
        super(AssignmentPoll, self).append_pollform_fields(fields)

    def get_slide_context(self, **context):
        return super(AssignmentPoll, self).get_slide_context(poll=self)

    def get_root_rest_element(self):
        """
        Returns the assignment to this instance which is the root REST element.
        """
        return self.assignment
