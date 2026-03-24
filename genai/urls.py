from django.urls import path
from . import views

app_name = 'genai'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('sso/login/', views.sso_login_view, name='sso_login'),
    path('logout/', views.logout_view, name='logout'),
    path('session/init/', views.chat_session_init_view, name='chat_session_init'),
    path('session/list/', views.chat_session_list_view, name='chat_session_list'),
    path('session/reset/', views.chat_session_reset_view, name='chat_session_reset'),
    path('app/assistant/', views.assistant_app_view, name='assistant_app'),
    path('chat/', views.genai_chat, name='chat'),
    path('applications/dashboard/', views.applications_dashboard_view, name='applications_dashboard'),
    path('applications/overview/', views.applications_overview_view, name='applications_overview'),
    path('applications/<str:application_key>/graph/', views.application_graph_view, name='application_graph'),
    path('predictions/recent/', views.recent_predictions_view, name='recent_predictions'),
    path('alerts/dashboard/', views.alerts_dashboard_view, name='alerts_dashboard'),
    path('alerts/ingest/', views.ingest_alert_view, name='ingest_alert'),
    path('alerts/recent/', views.recent_alert_recommendations_view, name='recent_alert_recommendations'),
    path('incidents/dashboard/', views.incidents_dashboard_view, name='incidents_dashboard'),
    path('incidents/recent/', views.incidents_recent_view, name='incidents_recent'),
    path('incidents/<str:incident_key>/', views.incident_timeline_page_view, name='incident_timeline_page'),
    path('incidents/<str:incident_key>/timeline/', views.incident_timeline_view, name='incident_timeline'),
    path('incidents/<str:incident_key>/graph/', views.incident_graph_view, name='incident_graph'),
    path('execute_command/', views.execute_command_view, name='execute_command'),
    path('download_excel/', views.download_excel, name='download_excel'),
    path('faq/', views.get_faq_questions, name='faq_questions'),
    path('console/', views.genai_console, name='genai_console'),
    path('widget/', views.widget_view, name='widget'),
]
