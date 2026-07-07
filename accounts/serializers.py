from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role", "is_staff"]
        read_only_fields = ["id", "role", "is_staff"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["email", "full_name", "phone", "password"]

    def validate_phone(self, value):
        value = (value or "").strip() or None
        if value and User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Ce téléphone est déjà utilisé.")
        return value

    def create(self, validated_data):
        # Inscription publique = toujours un compte CLIENT
        return User.objects.create_user(role=User.Role.CLIENT, **validated_data)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login email + mot de passe ; ajoute les infos utilisateur à la réponse."""
    username_field = User.USERNAME_FIELD  # "email"

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])


class OTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField()


class OTPVerifySerializer(serializers.Serializer):
    phone = serializers.CharField()
    code = serializers.CharField()
