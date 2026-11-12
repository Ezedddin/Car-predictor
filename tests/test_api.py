import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import main


class PredictionTests(unittest.TestCase):
    client = TestClient(main.app)
    payload = {
        "merk": "Volkswagen", "model": "Golf", "bouwjaar": 2020,
        "km": 91_234, "km_verkoop": 107_654, "verkoop_maanden": 13,
        "brandstof": "petrol", "transmissie": "manual",
    }

    def test_prediction_uses_model_and_returns_ordered_scenarios(self):
        response = self.client.post("/api/voorspel", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        points = response.json()["punten"]
        self.assertEqual([p["maanden"] for p in points], [0, 6, 12, 13])
        self.assertEqual(points[0]["km"], self.payload["km"])
        self.assertEqual(points[-1]["km"], self.payload["km_verkoop"])
        for p in points:
            self.assertTrue(0 < p["laag"] <= p["midden"] <= p["hoog"])

    def test_missing_cpi_returns_validation_error(self):
        with patch.object(main, "cpi", main.cpi.drop(2020)):
            response = self.client.post("/api/voorspel", json=self.payload)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("prijsindex", response.json()["detail"])

    def test_sale_mileage_cannot_go_backwards(self):
        response = self.client.post("/api/voorspel", json=self.payload | {"km_verkoop": 90_000})
        self.assertEqual(response.status_code, 422, response.text)
