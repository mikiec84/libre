from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('data_sets.views',
    url(r'^$', 'sources_view', name='sources_view'),
)
