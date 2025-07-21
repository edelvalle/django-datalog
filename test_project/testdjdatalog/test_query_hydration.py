"""
Tests for query hydration functionality in django_datalog.
"""

from unittest.mock import Mock, patch

from django.test import TestCase

from django_datalog.models import Var, query


class QueryHydrationTests(TestCase):
    """Test query hydration controls."""

    @patch("django_datalog.query._satisfy_conjunction_with_targeted_facts")
    @patch("django_datalog.query._hydrate_results")
    def test_hydration_enabled_calls_hydrate_results(self, mock_hydrate, mock_satisfy):
        """Test that hydrate=True calls _hydrate_results."""
        # Setup mocks
        mock_pk_results = [{"subject": 1, "object": 2}]
        mock_satisfy.return_value = iter(mock_pk_results)
        mock_hydrate.return_value = iter([{"subject": Mock(), "object": Mock()}])

        # Create test fact mock
        mock_fact = Mock()
        mock_fact.subject = Mock()
        mock_fact.object = Var("vessel")

        # Query with hydration enabled (default)
        list(query(mock_fact, hydrate=True))

        # Verify _satisfy_conjunction_with_targeted_facts was called
        mock_satisfy.assert_called_once()

        # Verify _hydrate_results was called with the PK results
        mock_hydrate.assert_called_once_with(mock_pk_results, [mock_fact])

    @patch("django_datalog.query._satisfy_conjunction_with_targeted_facts")
    @patch("django_datalog.query._hydrate_results")
    def test_hydration_disabled_skips_hydrate_results(self, mock_hydrate, mock_satisfy):
        """Test that hydrate=False skips _hydrate_results."""
        # Setup mocks
        mock_pk_results = [{"subject": 1, "object": 2}]
        mock_satisfy.return_value = iter(mock_pk_results)

        # Create test fact mock
        mock_fact = Mock()
        mock_fact.subject = Mock()
        mock_fact.object = Var("vessel")

        # Query with hydration disabled
        results = list(query(mock_fact, hydrate=False))

        # Verify _satisfy_conjunction_with_targeted_facts was called
        mock_satisfy.assert_called_once()

        # Verify _hydrate_results was NOT called
        mock_hydrate.assert_not_called()

        # Verify we got the PK results directly
        self.assertEqual(results, mock_pk_results)

    @patch("django_datalog.query._satisfy_conjunction_with_targeted_facts")
    def test_hydration_default_is_true(self, mock_satisfy):
        """Test that hydration defaults to True."""
        # Setup mocks
        mock_satisfy.return_value = iter([])

        # Create test fact mock
        mock_fact = Mock()
        mock_fact.subject = Mock()
        mock_fact.object = Var("vessel")

        # Query without specifying hydrate parameter
        with patch("django_datalog.query._hydrate_results") as mock_hydrate:
            mock_hydrate.return_value = iter([])
            list(query(mock_fact))  # No hydrate parameter

            # Should call hydrate_results (default behavior)
            mock_hydrate.assert_called_once()

    def test_query_function_signature(self):
        """Test that query function accepts hydrate parameter."""
        # This test ensures the function signature is correct
        import inspect

        from django_datalog.models import query

        sig = inspect.signature(query)

        # Check that hydrate parameter exists
        self.assertIn("hydrate", sig.parameters)

        # Check that hydrate defaults to True
        hydrate_param = sig.parameters["hydrate"]
        self.assertEqual(hydrate_param.default, True)
        self.assertEqual(hydrate_param.annotation, bool)
