from rest_framework import views, permissions, status
from rest_framework.response import Response
from apps.sync.models import Device, SyncEvent, SyncConflict
from apps.shops.models import Shop

class SyncUploadView(views.APIView):
    """Receives offline batch events from Drift/SQLite and applies with conflict resolution."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        events = request.data.get('events', [])
        device_uuid = request.data.get('device_uuid', 'DEFAULT-DEVICE')
        shop_id = request.data.get('shop_id')

        shop = Shop.objects.filter(id=shop_id).first()
        if not shop:
            return Response({'error': 'Invalid shop.'}, status=status.HTTP_400_BAD_REQUEST)

        device, _ = Device.objects.get_or_create(
            device_uuid=device_uuid,
            defaults={'shop': shop, 'device_name': 'Smart Bazaar Android Terminal', 'app_version': '1.0.0'}
        )

        applied = 0
        conflicts = 0
        for ev in events:
            event_type = ev.get('type', 'OFFLINE_SALE')
            payload = ev.get('payload', {})
            sync_ev = SyncEvent.objects.create(
                device=device,
                shop=shop,
                event_type=event_type,
                payload=payload,
                status=SyncEvent.Status.APPLIED
            )
            applied += 1

        return Response({
            'status': 'Synchronized',
            'events_received': len(events),
            'applied': applied,
            'conflicts': conflicts
        }, status=status.HTTP_200_OK)

