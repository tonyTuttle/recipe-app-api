"""Tests for ingredients API"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from core.models import Ingredient, Recipe
from recipe.serializers import IngredientSerializer

INGREDIENTS_URL = reverse("recipe:ingredient-list")


def create_user(email="user@example.com", password="testpass123"):
    """Create and return user"""
    return get_user_model().objects.create(email=email, password=password)


def detail_url(ingredient_id):
    """Create and return an ingredient detail url"""
    return reverse("recipe:ingredient-detail", args=[ingredient_id])


class PublicIngredientsApiTests(TestCase):
    """Test unauthenticated API requests"""

    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """Test auth is required for retrieving ingredients"""
        response = self.client.get(INGREDIENTS_URL)
        self.assertTrue(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateIngredientsApiTests(TestCase):
    """Test authenticated API requests"""

    def setUp(self):
        self.user = create_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_ingredients(self):
        """Test retrieving a list of ingredients"""
        Ingredient.objects.create(user=self.user, name="kale")
        Ingredient.objects.create(user=self.user, name="vanilla")
        response = self.client.get(INGREDIENTS_URL)
        ingredients = Ingredient.objects.all().order_by("-name")
        serializer = IngredientSerializer(ingredients, many=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, serializer.data)

    def test_ingredients_limited_to_user(self):
        """Test list of ingredients is limited to authenticated user"""
        other_user = create_user(
            email="other_user@example.com", password="testpass456"
        )
        Ingredient.objects.create(user=other_user, name="salt")
        ingredient = Ingredient.objects.create(user=self.user, name="pepper")
        response = self.client.get(INGREDIENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], ingredient.name)
        self.assertEqual(response.data[0]["id"], ingredient.id)

    def test_update_ingredient(self):
        """Test updating an ingredient"""
        ingredient = Ingredient.objects.create(user=self.user, name="cilantro")
        payload = {"name": "coriander"}
        url = detail_url(ingredient.id)
        response = self.client.patch(url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.name, payload["name"])

    def test_delete_ingredient(self):
        """Test deleting an ingredient"""
        ingredient = Ingredient.objects.create(user=self.user, name="lettuce")
        url = detail_url(ingredient.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        ingredients = Ingredient.objects.filter(user=self.user)
        self.assertFalse(ingredients.exists())

    def test_filter_ingredients_assigned_to_recipe(self):
        """Test listing ingredients by those assigned to recipes"""
        ingredient1 = Ingredient.objects.create(user=self.user, name="apple")
        ingredient2 = Ingredient.objects.create(user=self.user, name="turkey")
        recipe = Recipe.objects.create(
            title="Apple crumble",
            time_minutes=5,
            price=Decimal("4.50"),
            user=self.user,
        )
        recipe.ingredients.add(ingredient1)
        response = self.client.get(INGREDIENTS_URL, {"assigned_only": 1})
        serializer1 = IngredientSerializer(ingredient1)
        serializer2 = IngredientSerializer(ingredient2)
        self.assertIn(serializer1.data, response.data)
        self.assertNotIn(serializer2.data, response.data)

    def test_filtered_ingredients_unique(self):
        """Test filtered ingredients returns a unique list"""
        ingredient = Ingredient.objects.create(user=self.user, name="egg")
        Ingredient.objects.create(user=self.user, name="lentils")
        recipe1 = Recipe.objects.create(
            title="Eggs benedict",
            time_minutes=30,
            price=Decimal("5.00"),
            user=self.user,
        )
        recipe2 = Recipe.objects.create(
            title="Herb eggs",
            time_minutes=20,
            price=Decimal("6.00"),
            user=self.user,
        )
        recipe1.ingredients.add(ingredient)
        recipe2.ingredients.add(ingredient)
        response = self.client.get(INGREDIENTS_URL, {"assigned_only": 1})

        self.assertEqual(len(response.data), 1)
