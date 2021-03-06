from django.core.urlresolvers import reverse

from openslides.utils.utils import int_or_none


class SlideMixin(object):
    """
    A Mixin for a Django-Model, for making the model a slide.
    """

    slide_callback_name = None
    """
    Name of the callback to render the model as slide.
    """

    def get_absolute_url(self, link='projector'):
        """
        Return the url to activate the slide, if link == 'projector'.
        """
        if link in ('projector', 'projector_preview'):
            url_name = {'projector': 'projector_activate_slide',
                        'projector_preview': 'projector_preview'}[link]
            value = '%s?pk=%d' % (
                reverse(url_name,
                        args=[self.slide_callback_name]),
                self.pk)
        else:
            value = super(SlideMixin, self).get_absolute_url(link)
        return value

    def is_active_slide(self):
        """
        Return True, if the the slide is the active slide.
        """
        from openslides.projector.api import get_active_slide
        active_slide = get_active_slide()
        slide_pk = int_or_none(active_slide.get('pk', None))
        return (active_slide['callback'] == self.slide_callback_name and
                self.pk == slide_pk)

    def get_slide_context(self, **context):
        """
        Returns the context for the template which renders the slide.
        """
        slide_name = self._meta.object_name.lower()
        context.update({'slide': self,
                        slide_name: self})
        return context
