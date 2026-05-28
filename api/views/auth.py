from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class GetTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '')
        password = request.data.get('password', '')
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({'error': 'Invalid credentials'}, status=401)

        from webapp.models import APIToken
        token = APIToken.objects.filter(user=user).order_by('-created').first()
        if not token:
            token = APIToken.objects.create(user=user, name='Default')
        return Response({'token': token.key, 'username': user.username})


class CheckTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'valid': True, 'username': request.user.username})
