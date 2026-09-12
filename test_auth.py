import unittest
from datetime import timedelta

from streamlit.testing.v1 import AppTest
from auth import authenticate, hash_password, verify_password, brasilia_now


class LoginTests(unittest.TestCase):
    def app(self, role="ADMIN"):
        app = AppTest.from_file("app.py", default_timeout=30)
        app.secrets["auth"] = {"users": {"teste": {
            "username": "teste", "email": "teste@example.com", "name": "Teste",
            "password": "senha-teste", "role": role,
        }}}
        return app.run()

    def submit(self, app, password="senha-teste"):
        app.text_input[0].set_value("teste@example.com")
        app.text_input[1].set_value(password)
        return app.button[0].click().run()

    def test_password_hash(self):
        hashed = hash_password("senha-á")
        self.assertTrue(verify_password("senha-á", hashed))
        self.assertFalse(verify_password("errada", hashed))
        self.assertIsNone(authenticate("inexistente", "errada", {}))

    def test_login_logout_and_timeout(self):
        app = self.app()
        self.assertFalse(app.sidebar.radio)
        self.submit(app, "incorreta")
        self.assertFalse(app.sidebar.radio)
        self.submit(app)
        self.assertFalse(app.exception)
        self.assertIn("Importações", app.sidebar.radio[0].options)
        app.sidebar.button[0].click().run()
        self.assertFalse(app.sidebar.radio)
        self.submit(app)
        app.session_state["last_activity"] = brasilia_now() - timedelta(minutes=61)
        app.run()
        self.assertFalse(app.sidebar.radio)

    def test_read_only_profile(self):
        app = self.submit(self.app("CONSULTA"))
        self.assertFalse(app.exception)
        self.assertNotIn("Importações", app.sidebar.radio[0].options)

    def test_lockout(self):
        app = self.app()
        for _ in range(5):
            self.submit(app, "incorreta")
        app.run()
        self.assertFalse(app.text_input)
        self.assertFalse(app.sidebar.radio)
        self.assertIn("Muitas tentativas", app.error[0].value)


if __name__ == "__main__":
    unittest.main()
