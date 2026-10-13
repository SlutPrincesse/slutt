"""
RBAC Inspector - Role-Based Access Control auditing and validation
"""
import hashlib
import json
import time
from typing import Dict, List, Optional, Any, Set, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict


class Permission(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    ADMIN = "admin"
    CREATE = "create"
    UPDATE = "update"
    LIST = "list"


class ResourceType(Enum):
    FILE = "file"
    DATABASE = "database"
    API = "api"
    SERVICE = "service"
    CONFIG = "config"
    SECRET = "secret"
    USER = "user"
    ROLE = "role"


@dataclass
class Role:
    role_id: str
    name: str
    permissions: Dict[ResourceType, Set[Permission]] = field(default_factory=dict)
    parent_roles: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def has_permission(self, resource: ResourceType, permission: Permission) -> bool:
        return permission in self.permissions.get(resource, set())

    def add_permission(self, resource: ResourceType, permission: Permission):
        if resource not in self.permissions:
            self.permissions[resource] = set()
        self.permissions[resource].add(permission)

    def remove_permission(self, resource: ResourceType, permission: Permission):
        if resource in self.permissions:
            self.permissions[resource].discard(permission)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "permissions": {r.value: [p.value for p in perms] for r, perms in self.permissions.items()},
            "parent_roles": self.parent_roles,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class User:
    user_id: str
    username: str
    roles: List[str] = field(default_factory=list)
    direct_permissions: Dict[ResourceType, Set[Permission]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_login: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": self.roles,
            "direct_permissions": {r.value: [p.value for p in perms] for r, perms in self.direct_permissions.items()},
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }


@dataclass
class AccessControlEntry:
    ace_id: str
    resource_type: ResourceType
    resource_id: str
    role_id: str
    permissions: Set[Permission] = field(default_factory=set)
    effect: str = "allow"
    conditions: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ace_id": self.ace_id,
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "role_id": self.role_id,
            "permissions": [p.value for p in self.permissions],
            "effect": self.effect,
            "conditions": self.conditions,
            "created_at": self.created_at,
        }


@dataclass
class RBACViolation:
    violation_id: str
    user_id: str
    resource_type: ResourceType
    resource_id: str
    attempted_permission: Permission
    required_permissions: Set[Permission]
    user_roles: List[str]
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "user_id": self.user_id,
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "attempted_permission": self.attempted_permission.value,
            "required_permissions": [p.value for p in self.required_permissions],
            "user_roles": self.user_roles,
            "timestamp": self.timestamp,
            "context": self.context,
        }


class RBACInspector:
    def __init__(self):
        self.roles: Dict[str, Role] = {}
        self.users: Dict[str, User] = {}
        self.aces: List[AccessControlEntry] = []
        self.violations: List[RBACViolation] = []
        self._role_hierarchy_cache: Dict[str, Set[str]] = {}
        self._user_permissions_cache: Dict[str, Dict[ResourceType, Set[Permission]]] = {}

    def create_role(self, name: str, role_id: str = None) -> Role:
        role_id = role_id or hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12]
        role = Role(role_id=role_id, name=name)
        self.roles[role_id] = role
        self._invalidate_cache()
        return role

    def create_user(self, username: str, user_id: str = None) -> User:
        user_id = user_id or hashlib.md5(f"{username}:{time.time()}".encode()).hexdigest()[:12]
        user = User(user_id=user_id, username=username)
        self.users[user_id] = user
        self._invalidate_cache()
        return user

    def assign_role(self, user_id: str, role_id: str) -> bool:
        if user_id not in self.users or role_id not in self.roles:
            return False
        if role_id not in self.users[user_id].roles:
            self.users[user_id].roles.append(role_id)
            self._invalidate_cache()
        return True

    def revoke_role(self, user_id: str, role_id: str) -> bool:
        if user_id in self.users:
            self.users[user_id].roles = [r for r in self.users[user_id].roles if r != role_id]
            self._invalidate_cache()
            return True
        return False

    def grant_permission_to_role(self, role_id: str, resource: ResourceType, permission: Permission) -> bool:
        if role_id in self.roles:
            self.roles[role_id].add_permission(resource, permission)
            self._invalidate_cache()
            return True
        return False

    def add_ace(self, resource_type: ResourceType, resource_id: str, role_id: str, 
                permissions: Set[Permission], effect: str = "allow") -> AccessControlEntry:
        ace = AccessControlEntry(
            ace_id=hashlib.md5(f"{resource_type}:{resource_id}:{role_id}:{time.time()}".encode()).hexdigest()[:12],
            resource_type=resource_type,
            resource_id=resource_id,
            role_id=role_id,
            permissions=permissions,
            effect=effect,
        )
        self.aces.append(ace)
        self._invalidate_cache()
        return ace

    def check_access(self, user_id: str, resource_type: ResourceType, resource_id: str, 
                     permission: Permission, context: Dict = None) -> Tuple[bool, Optional[RBACViolation]]:
        user = self.users.get(user_id)
        if not user:
            violation = RBACViolation(
                violation_id=hashlib.md5(f"violation:{user_id}:{time.time()}".encode()).hexdigest()[:12],
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                attempted_permission=permission,
                required_permissions={permission},
                user_roles=[],
                context=context or {},
            )
            self.violations.append(violation)
            return False, violation
        
        user_perms = self._get_user_effective_permissions(user_id)
        has_perm = permission in user_perms.get(resource_type, set())
        
        if not has_perm:
            required_perms = {permission}
            for ace in self.aces:
                if ace.resource_type == resource_type and ace.resource_id == resource_id:
                    if ace.effect == "allow" and permission in ace.permissions:
                        required_perms.add(permission)
            
            violation = RBACViolation(
                violation_id=hashlib.md5(f"violation:{user_id}:{resource_id}:{time.time()}".encode()).hexdigest()[:12],
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                attempted_permission=permission,
                required_permissions=required_perms,
                user_roles=user.roles,
                context=context or {},
            )
            self.violations.append(violation)
            return False, violation
        
        return True, None

    def _get_user_effective_permissions(self, user_id: str) -> Dict[ResourceType, Set[Permission]]:
        if user_id in self._user_permissions_cache:
            return self._user_permissions_cache[user_id]
        
        user = self.users.get(user_id)
        if not user:
            return {}
        
        effective_perms: Dict[ResourceType, Set[Permission]] = defaultdict(set)
        
        for resource, perms in user.direct_permissions.items():
            effective_perms[resource].update(perms)
        
        all_roles = self._get_all_roles_for_user(user_id)
        for role_id in all_roles:
            role = self.roles.get(role_id)
            if role:
                for resource, perms in role.permissions.items():
                    effective_perms[resource].update(perms)
        
        for ace in self.aces:
            if ace.role_id in all_roles and ace.effect == "allow":
                effective_perms[ace.resource_type].update(ace.permissions)
        
        self._user_permissions_cache[user_id] = dict(effective_perms)
        return dict(effective_perms)

    def _get_all_roles_for_user(self, user_id: str) -> Set[str]:
        user = self.users.get(user_id)
        if not user:
            return set()
        
        all_roles = set(user.roles)
        for role_id in user.roles:
            all_roles.update(self._get_role_hierarchy(role_id))
        return all_roles

    def _get_role_hierarchy(self, role_id: str) -> Set[str]:
        if role_id in self._role_hierarchy_cache:
            return self._role_hierarchy_cache[role_id]
        
        role = self.roles.get(role_id)
        if not role:
            return set()
        
        hierarchy = set()
        for parent_id in role.parent_roles:
            hierarchy.add(parent_id)
            hierarchy.update(self._get_role_hierarchy(parent_id))
        
        self._role_hierarchy_cache[role_id] = hierarchy
        return hierarchy

    def _invalidate_cache(self):
        self._role_hierarchy_cache.clear()
        self._user_permissions_cache.clear()

    def audit_rbac(self) -> Dict[str, Any]:
        issues = []
        warnings = []
        
        for user_id, user in self.users.items():
            if not user.roles:
                warnings.append(f"User {user.username} has no roles assigned")
            
            perms = self._get_user_effective_permissions(user_id)
            for resource, permissions in perms.items():
                if Permission.ADMIN in permissions and resource == ResourceType.SECRET:
                    issues.append(f"User {user.username} has admin access to secrets")
        
        for role_id, role in self.roles.items():
            if not role.permissions:
                warnings.append(f"Role {role.name} has no permissions")
            
            for resource, permissions in role.permissions.items():
                if Permission.ADMIN in permissions and resource in [ResourceType.SECRET, ResourceType.CONFIG]:
                    issues.append(f"Role {role.name} has admin access to {resource.value}")
        
        for ace in self.aces:
            if ace.effect == "allow" and Permission.ADMIN in ace.permissions:
                if ace.resource_type in [ResourceType.SECRET, ResourceType.CONFIG]:
                    issues.append(f"ACE {ace.ace_id} grants admin access to {ace.resource_type.value}")
        
        return {
            "total_users": len(self.users),
            "total_roles": len(self.roles),
            "total_aces": len(self.aces),
            "total_violations": len(self.violations),
            "issues": issues,
            "warnings": warnings,
            "compliance_score": max(0, 100 - len(issues) * 10 - len(warnings) * 2),
        }

    def get_violations(self, user_id: str = None, limit: int = 100) -> List[RBACViolation]:
        violations = self.violations
        if user_id:
            violations = [v for v in violations if v.user_id == user_id]
        return violations[-limit:]

    def export_policy(self, format: str = "json") -> str:
        if format == "json":
            return json.dumps({
                "roles": {k: v.to_dict() for k, v in self.roles.items()},
                "users": {k: v.to_dict() for k, v in self.users.items()},
                "aces": [ace.to_dict() for ace in self.aces],
            }, indent=2)
        return ""

    def import_policy(self, policy_json: str) -> bool:
        try:
            data = json.loads(policy_json)
            self.roles = {k: Role(**v) for k, v in data.get("roles", {}).items()}
            self.users = {k: User(**v) for k, v in data.get("users", {}).items()}
            self.aces = [AccessControlEntry(**ace) for ace in data.get("aces", [])]
            self._invalidate_cache()
            return True
        except Exception:
            return False


class RBACPolicyEngine:
    def __init__(self, inspector: RBACInspector):
        self.inspector = inspector

    def enforce_least_privilege(self, user_id: str) -> Dict[str, List[str]]:
        user = self.inspector.users.get(user_id)
        if not user:
            return {}
        
        current_perms = self.inspector._get_user_effective_permissions(user_id)
        recommendations = {}
        
        for resource, permissions in current_perms.items():
            if Permission.ADMIN in permissions:
                recommendations.setdefault("remove_admin", []).append(
                    f"User has admin on {resource.value}"
                )
        
        return recommendations

    def detect_privilege_escalation_paths(self) -> List[Dict[str, Any]]:
        paths = []
        
        for user_id, user in self.inspector.users.items():
            perms = self.inspector._get_user_effective_permissions(user_id)
            roles = self.inspector._get_all_roles_for_user(user_id)
            
            for role_id in roles:
                role = self.inspector.roles.get(role_id)
                if role and Permission.ADMIN in role.permissions.get(ResourceType.ROLE, set()):
                    paths.append({
                        "user": user.username,
                        "role": role.name,
                        "path": "Can assign roles -> privilege escalation",
                    })
        
        return paths

    def generate_segregation_of_duties_report(self) -> Dict[str, Any]:
        conflicts = []
        
        sod_pairs = [
            (Permission.CREATE, Permission.APPROVE),
            (Permission.WRITE, Permission.DELETE),
            (Permission.READ, Permission.ADMIN),
        ]
        
        for user_id, user in self.inspector.users.items():
            perms = self.inspector._get_user_effective_permissions(user_id)
            for resource, permissions in perms.items():
                for p1, p2 in sod_pairs:
                    if p1 in permissions and p2 in permissions:
                        conflicts.append({
                            "user": user.username,
                            "resource": resource.value,
                            "conflict": f"{p1.value} + {p2.value}",
                        })
        
        return {
            "total_users_checked": len(self.inspector.users),
            "conflicts_found": len(conflicts),
            "conflicts": conflicts,
        }