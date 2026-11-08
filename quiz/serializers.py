from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from quiz.models import Category, QuizSession
from quiz.validators import validate_player_name


class CategorySerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "color", "icon", "question_count"]


class StartSessionSerializer(serializers.Serializer):
    category = serializers.SlugField()
    platform = serializers.ChoiceField(choices=QuizSession.Platform.choices, default="web")
    language = serializers.CharField(max_length=10, required=False, allow_blank=True)


class AnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    choice_id = serializers.IntegerField(allow_null=True)


class NameSerializer(serializers.Serializer):
    player_name = serializers.CharField(max_length=100)

    def validate_player_name(self, value):
        try:
            return validate_player_name(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
