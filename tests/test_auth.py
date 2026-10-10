import pytest

from counterx.services import AuthenticationError, PermissionDenied


def test_create_and_login(auth, owner):
    user = auth.authenticate("owner", "owner1234")
    assert user.username == "owner"
    with pytest.raises(AuthenticationError):
        auth.authenticate("owner", "wrong")
    with pytest.raises(AuthenticationError):
        auth.authenticate("nobody", "x")


def test_duplicate_username(auth, owner):
    with pytest.raises(ValueError):
        auth.create_user("owner", "anotherpass", role="cashier")


def test_role_permissions(auth, owner, cashier):
    assert auth.has_permission(owner, "void")
    assert auth.has_permission(owner, "users")
    assert not auth.has_permission(cashier, "void")
    assert auth.has_permission(cashier, "sell")
    with pytest.raises(PermissionDenied):
        auth.require(cashier, "void")


def test_permission_override_grant(auth, owner, cashier):
    auth.set_override(cashier, "discount", True, owner)
    assert auth.has_permission(cashier, "discount")


def test_permission_override_revoke(auth, owner):
    mgr = auth.create_user("mgr", "mgr1234", role="manager")
    assert auth.has_permission(mgr, "void")
    auth.set_override(mgr, "void", False, owner)
    assert not auth.has_permission(mgr, "void")


def test_only_owner_manages_users(auth, owner, cashier):
    with pytest.raises(PermissionDenied):
        auth.create_user("x", "x1234", role="cashier", actor=cashier)


def test_change_password(auth, owner):
    auth.change_password(owner, "newpass99")
    auth.authenticate("owner", "newpass99")
    with pytest.raises(AuthenticationError):
        auth.authenticate("owner", "owner1234")
