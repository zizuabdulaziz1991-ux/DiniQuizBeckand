import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from quiz.models import Category, Choice, Question


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def category(db):
    return Category.objects.create(name="Siyer", slug="siyer")


@pytest.fixture
def questions(category):
    qs = []
    for i in range(5):
        q = Question.objects.create(category=category, text=f"Soru {i}", is_approved=True, explanation="açıklama")
        for j in range(4):
            Choice.objects.create(question=q, text=f"Şık {j}", is_correct=(j == 0))
        qs.append(q)
    return qs
