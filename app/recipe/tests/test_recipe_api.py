"""Tests for recipe api"""

import tempfile
import os
from PIL import Image
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from core.models import Recipe, Tag, Ingredient
from recipe.serializers import RecipeSerializer, RecipeDetailSerializer

RECIPES_URL = reverse("recipe:recipe-list")


def detail_url(recipe_id):
    """Create and return a recipe detail url"""
    return reverse("recipe:recipe-detail", args=[recipe_id])


def image_upload_url(recipe_id):
    """Create and return an image upload url"""
    return reverse("recipe:recipe-upload-image", args=[recipe_id])


def create_recipe(user, **params):
    """Create and return a sample recipe"""
    defaults = {
        "title": "sample recipe title",
        "time_minutes": 22,
        "price": Decimal("5.25"),
        "description": "sample description",
        "link": "http://example.com/recipe.pdf",
    }
    defaults.update(params)
    recipe = Recipe.objects.create(user=user, **defaults)
    return recipe


def create_user(**params):
    """Create and return a new user"""
    return get_user_model().objects.create_user(**params)


class PublicRecipeAPITests(TestCase):
    """Test unauthenticated api requests"""

    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """Test auth is required to call api"""
        response = self.client.get(RECIPES_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateRecipeAPITests(TestCase):
    """Test authenticated api requests"""

    def setUp(self):
        self.client = APIClient()
        self.user = create_user(
            email="test@example.com", password="testpass123"
        )
        self.client.force_authenticate(self.user)

    def test_retrieve_recipe(self):
        """Test retrieving a list of recipes"""
        create_recipe(user=self.user)
        create_recipe(user=self.user)
        response = self.client.get(RECIPES_URL)
        recipes = Recipe.objects.all().order_by("-id")
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        """Test list of recipes is limited to authenticated user"""
        other_user = create_user(
            email="other@example.com", password="testpass456"
        )
        create_recipe(user=other_user)
        create_recipe(user=self.user)
        response = self.client.get(RECIPES_URL)
        recipes = Recipe.objects.filter(user=self.user)
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, serializer.data)

    def test_get_recipe_detail(self):
        """Test get recipe detail"""
        recipe = create_recipe(user=self.user)
        url = detail_url(recipe.id)
        response = self.client.get(url)
        serializer = RecipeDetailSerializer(recipe)
        self.assertEqual(response.data, serializer.data)

    def test_create_recipe(self):
        """Test creating a recipe"""
        payload = {
            "title": "sample recipe",
            "time_minutes": 30,
            "price": Decimal("5.99"),
        }
        response = self.client.post(RECIPES_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        recipe = Recipe.objects.get(id=response.data["id"])
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_partial_update(self):
        """Test partial update of a recipe"""
        original_link = "https://example.com/recipe.pdf"
        recipe = create_recipe(
            user=self.user, title="Sample recipe title", link=original_link
        )
        payload = {"title": "New recipe title"}
        url = detail_url(recipe.id)
        response = self.client.patch(url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.title, payload["title"])
        self.assertEqual(recipe.link, original_link)
        self.assertEqual(recipe.user, self.user)

    def test_full_update(self):
        """Test full update of recipe"""
        recipe = create_recipe(
            user=self.user,
            title="Sample recipe title",
            link="https://example.com/recipe.pdf",
            description="Sample recipe description",
        )
        payload = {
            "title": "New recipe title",
            "link": "https://example.com/new-recipe.pdf",
            "time_minutes": 10,
            "price": Decimal("2.50"),
        }
        url = detail_url(recipe.id)
        response = self.client.put(url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_update_user_returns_error(self):
        """Test changing recipe user results in error"""
        new_user = create_user(
            email="newuser@example.com", password="testpass456"
        )
        recipe = create_recipe(user=self.user)
        payload = {"user": new_user.id}
        url = detail_url(recipe.id)
        self.client.patch(url, payload)
        recipe.refresh_from_db()
        self.assertEqual(recipe.user, self.user)

    def test_delete_recipe(self):
        """Test deleting a recipe successful"""
        recipe = create_recipe(user=self.user)
        url = detail_url(recipe.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recipe.objects.filter(id=recipe.id).exists())

    def test_delete_other_users_recipe_error(self):
        """Test deleting other user's recipe returns error"""
        new_user = create_user(
            email="newuser@example.com", password="testpass456"
        )
        recipe = create_recipe(user=new_user)
        url = detail_url(recipe.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Recipe.objects.filter(id=recipe.id).exists())

    def test_create_recipe_with_new_tags(self):
        """Test creating a recipe with new tags"""
        payload = {
            "title": "Thai prawn curry",
            "time_minutes": 30,
            "price": Decimal("2.50"),
            "tags": [{"name": "Thai"}, {"name": "Dinner"}],
        }
        response = self.client.post(RECIPES_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.tags.count(), 2)
        for tag in payload["tags"]:
            exists = recipe.tags.filter(
                name=tag["name"], user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_existing_tags(self):
        """Test creating a recipe with an existing tag"""
        tag_indian = Tag.objects.create(user=self.user, name="Indian")
        payload = {
            "title": "Pongal",
            "time_minutes": 60,
            "price": Decimal("4.50"),
            "tags": [{"name": "Indian"}, {"name": "Breakfast"}],
        }
        response = self.client.post(RECIPES_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.tags.count(), 2)
        self.assertIn(tag_indian, recipe.tags.all())
        for tag in payload["tags"]:
            exists = recipe.tags.filter(
                name=tag["name"], user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_create_tag_on_update(self):
        """Test creating a tag when updating a recipe"""
        recipe = create_recipe(user=self.user)
        payload = {"tags": [{"name": "Lunch"}]}
        url = detail_url(recipe.id)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_tag = Tag.objects.get(user=self.user, name="Lunch")
        self.assertIn(new_tag, recipe.tags.all())

    def test_update_recipe_assign_tag(self):
        """Test assigning an existing tag when updating a recipe"""
        tag_breakfast = Tag.objects.create(user=self.user, name="Breakfast")
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag_breakfast)
        tag_lunch = Tag.objects.create(user=self.user, name="Lunch")
        payload = {"tags": [{"name": "Lunch"}]}
        url = detail_url(recipe.id)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(tag_lunch, recipe.tags.all())
        self.assertNotIn(tag_breakfast, recipe.tags.all())

    def test_clear_recipe_tags(self):
        """Test clearing a recipe's tags"""
        tag = Tag.objects.create(user=self.user, name="Dessert")
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag)
        payload = {"tags": []}
        url = detail_url(recipe.id)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.tags.count(), 0)

    def test_create_recipe_with_new_ingredients(self):
        """Test creating a recipe with new ingredients"""
        payload = {
            "title": "Cauliflower tacos",
            "time_minutes": 20,
            "price": Decimal("4.30"),
            "ingredients": [{"name": "cauliflower"}, {"name": "salt"}],
        }
        response = self.client.post(RECIPES_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.ingredients.count(), 2)
        for ingredient in payload["ingredients"]:
            exists = recipe.ingredients.filter(
                name=ingredient["name"]
            ).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_existing_ingredient(self):
        """Test creating a new recipe with existing ingredients"""
        ingredient = Ingredient.objects.create(user=self.user, name="lemon")
        payload = {
            "title": "Vietnamese soup",
            "time_minutes": 25,
            "price": Decimal("2.55"),
            "ingredients": [{"name": "lemon"}, {"name": "fish sauce"}],
        }
        response = self.client.post(RECIPES_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.ingredients.count(), 2)
        self.assertIn(ingredient, recipe.ingredients.all())
        for ingredient in payload["ingredients"]:
            exists = recipe.ingredients.filter(
                name=ingredient["name"], user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_create_ingredient_on_update(self):
        """Test creating an ingredient when updating a recipe"""
        recipe = create_recipe(user=self.user)
        payload = {"ingredients": [{"name": "lime"}]}
        url = detail_url(recipe.id)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_ingredient = Ingredient.objects.get(user=self.user, name="lime")
        self.assertIn(new_ingredient, recipe.ingredients.all())

    def test_update_recipe_assign_ingredient(self):
        """Test assigning an existing ingredient when updating a recipe"""
        ingredient1 = Ingredient.objects.create(user=self.user, name="pepper")
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient1)
        ingredient2 = Ingredient.objects.create(user=self.user, name="chili")
        payload = {"ingredients": [{"name": "chili"}]}
        url = detail_url(recipe.id)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(ingredient2, recipe.ingredients.all())
        self.assertNotIn(ingredient1, recipe.ingredients.all())

    def test_clear_recipe_ingredients(self):
        """Test clearing a recipe's ingredients"""
        ingredient = Ingredient.objects.create(user=self.user, name="garlic")
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient)
        payload = {"ingredients": []}
        url = detail_url(recipe.id)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.ingredients.count(), 0)

    def test_filter_by_tags(self):
        """Test filtering recipes by tags"""
        recipe1 = create_recipe(user=self.user, title="Thai vegetable curry")
        recipe2 = create_recipe(user=self.user, title="Aubergine with tahini")
        tag1 = Tag.objects.create(user=self.user, name="vegan")
        tag2 = Tag.objects.create(user=self.user, name="vegetarian")
        recipe1.tags.add(tag1)
        recipe2.tags.add(tag2)
        recipe3 = create_recipe(user=self.user, title="Fish and chips")
        params = {"tags": f"{tag1.id},{tag2.id}"}
        response = self.client.get(RECIPES_URL, params)
        serializer1 = RecipeSerializer(recipe1)
        serializer2 = RecipeSerializer(recipe2)
        serializer3 = RecipeSerializer(recipe3)
        self.assertIn(serializer1.data, response.data)
        self.assertIn(serializer2.data, response.data)
        self.assertNotIn(serializer3.data, response.data)

    def test_filter_by_ingredients(self):
        """Test filtering recipes by ingredients"""
        recipe1 = create_recipe(user=self.user, title="Posh beans on toast")
        recipe2 = create_recipe(user=self.user, title="Chicken cacciatore")
        ingredient1 = Ingredient.objects.create(
            user=self.user, name="feta cheese"
        )
        ingredient2 = Ingredient.objects.create(user=self.user, name="chicken")
        recipe1.ingredients.add(ingredient1)
        recipe2.ingredients.add(ingredient2)
        recipe3 = create_recipe(user=self.user, title="Red lentil daal")
        params = {"ingredients": f"{ingredient1.id},{ingredient2.id}"}
        response = self.client.get(RECIPES_URL, params)
        serializer1 = RecipeSerializer(recipe1)
        serializer2 = RecipeSerializer(recipe2)
        serializer3 = RecipeSerializer(recipe3)
        self.assertIn(serializer1.data, response.data)
        self.assertIn(serializer2.data, response.data)
        self.assertNotIn(serializer3.data, response.data)


class ImageUploadTests(TestCase):
    """Tests for the image upload api"""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            "user@example.com", "testpass123"
        )
        self.client.force_authenticate(self.user)
        self.recipe = create_recipe(user=self.user)

    def tearDown(self):
        self.recipe.image.delete()

    def test_upload_image(self):
        """Test uploading an image to a recipe"""
        url = image_upload_url(self.recipe.id)
        with tempfile.NamedTemporaryFile(suffix=".jpg") as image_file:
            img = Image.new("RGB", (10, 10))
            img.save(image_file, format="JPEG")
            image_file.seek(0)
            payload = {"image": image_file}
            response = self.client.post(url, payload, format="multipart")
        self.recipe.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("image", response.data)
        self.assertTrue(os.path.exists(self.recipe.image.path))

    def test_upload_image_bad_request(self):
        """Test uploading invalid image"""
        url = image_upload_url(self.recipe.id)
        payload = {"image": "not-an-image"}
        response = self.client.post(url, payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
