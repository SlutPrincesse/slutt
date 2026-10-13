"""
Timing Validator - Timing attack detection and prevention
"""
import hmac
import random
import statistics
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TimingAttackType(Enum):
    STRING_COMPARISON = "string_comparison"
    ARRAY_COMPARISON = "array_comparison"
    HMAC_VERIFICATION = "hmac_verification"
    PASSWORD_CHECK = "password_check"
    TOKEN_VALIDATION = "token_validation"
    CACHE_TIMING = "cache_timing"


@dataclass
class TimingMeasurement:
    operation: str
    duration_ns: int
    input_size: int
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimingAnalysisResult:
    operation: str
    vulnerable: bool
    confidence: float
    timing_variance: float
    correlation_coefficient: float
    sample_count: int
    attack_type: TimingAttackType = TimingAttackType.STRING_COMPARISON
    recommendations: list[str] = field(default_factory=list)


class TimingValidator:
    def __init__(self, samples_per_test: int = 1000):
        self.samples_per_test = samples_per_test
        self.measurements: dict[str, list[TimingMeasurement]] = defaultdict(list)
        self.results: dict[str, TimingAnalysisResult] = {}

    def measure_operation(self, operation: str, func: Callable, *args, **kwargs) -> tuple[Any, int]:
        start = time.perf_counter_ns()
        result = func(*args, **kwargs)
        duration = time.perf_counter_ns() - start

        measurement = TimingMeasurement(
            operation=operation,
            duration_ns=duration,
            input_size=len(str(args)) + len(str(kwargs)),
        )
        self.measurements[operation].append(measurement)

        return result, duration

    async def measure_async_operation(self, operation: str, func: Callable, *args, **kwargs) -> tuple[Any, int]:
        start = time.perf_counter_ns()
        result = await func(*args, **kwargs)
        duration = time.perf_counter_ns() - start

        measurement = TimingMeasurement(
            operation=operation,
            duration_ns=duration,
            input_size=len(str(args)) + len(str(kwargs)),
        )
        self.measurements[operation].append(measurement)

        return result, duration

    def analyze_timing(self, operation: str, attack_type: TimingAttackType = TimingAttackType.STRING_COMPARISON) -> TimingAnalysisResult:
        measurements = self.measurements.get(operation, [])

        if len(measurements) < 10:
            return TimingAnalysisResult(
                operation=operation,
                vulnerable=False,
                confidence=0.0,
                timing_variance=0.0,
                correlation_coefficient=0.0,
                sample_count=len(measurements),
                attack_type=attack_type,
                recommendations=["Insufficient samples for analysis"],
            )

        durations = [m.duration_ns for m in measurements]
        input_sizes = [m.input_size for m in measurements]

        mean_duration = statistics.mean(durations)
        variance = statistics.variance(durations) if len(durations) > 1 else 0
        stdev = statistics.stdev(durations) if len(durations) > 1 else 0

        correlation = self._calculate_correlation(input_sizes, durations)

        cv = stdev / mean_duration if mean_duration > 0 else 0

        vulnerable = cv > 0.05 and abs(correlation) > 0.3
        confidence = min(1.0, (cv * 10 + abs(correlation)) / 2)

        recommendations = []
        if vulnerable:
            recommendations.append("Use constant-time comparison functions")
            recommendations.append("Add random timing jitter")
            if attack_type == TimingAttackType.HMAC_VERIFICATION:
                recommendations.append("Use hmac.compare_digest() for HMAC verification")
            elif attack_type == TimingAttackType.PASSWORD_CHECK:
                recommendations.append("Use constant-time password hashing verification")

        result = TimingAnalysisResult(
            operation=operation,
            vulnerable=vulnerable,
            confidence=confidence,
            timing_variance=variance,
            correlation_coefficient=correlation,
            sample_count=len(measurements),
            attack_type=attack_type,
            recommendations=recommendations,
        )

        self.results[operation] = result
        return result

    def _calculate_correlation(self, x: list[float], y: list[float]) -> float:
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(len(x)))
        denom_x = sum((x[i] - mean_x) ** 2 for i in range(len(x)))
        denom_y = sum((y[i] - mean_y) ** 2 for i in range(len(y)))

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return numerator / (denom_x ** 0.5 * denom_y ** 0.5)

    def constant_time_compare(self, a: bytes, b: bytes) -> bool:
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= x ^ y
        return result == 0

    def constant_time_compare_str(self, a: str, b: str) -> bool:
        return self.constant_time_compare(a.encode(), b.encode())

    def verify_hmac_constant_time(self, expected: bytes, actual: bytes) -> bool:
        return hmac.compare_digest(expected, actual)

    def add_jitter(self, min_ns: int = 1000, max_ns: int = 10000):
        time.sleep(random.uniform(min_ns / 1e9, max_ns / 1e9))

    def get_measurements(self, operation: str) -> list[TimingMeasurement]:
        return self.measurements.get(operation, [])

    def clear_measurements(self, operation: str = None):
        if operation:
            self.measurements[operation].clear()
        else:
            self.measurements.clear()


class TimingAttackSimulator:
    def __init__(self, validator: TimingValidator):
        self.validator = validator

    def simulate_string_comparison_attack(self, target_func: Callable[[str], bool],
                                          target_string: str,
                                          charset: str = "abcdefghijklmnopqrstuvwxyz0123456789",
                                          max_length: int = 32) -> dict[str, Any]:
        discovered = ""

        for pos in range(max_length):
            best_char = None
            best_time = 0

            for char in charset:
                test_string = discovered + char + "a" * (max_length - pos - 1)

                times = []
                for _ in range(100):
                    start = time.perf_counter_ns()
                    target_func(test_string)
                    times.append(time.perf_counter_ns() - start)

                avg_time = statistics.mean(times)
                if avg_time > best_time:
                    best_time = avg_time
                    best_char = char

            if best_char:
                discovered += best_char
                if target_func(discovered + "a" * (max_length - len(discovered))):
                    break

        return {
            "discovered_prefix": discovered,
            "success": target_func(discovered),
            "target_length": len(target_string),
        }

    def simulate_cache_timing_attack(self, access_func: Callable[[int], Any],
                                     cache_size: int = 1000) -> dict[str, Any]:
        access_times = {}

        for i in range(cache_size * 2):
            times = []
            for _ in range(100):
                start = time.perf_counter_ns()
                access_func(i)
                times.append(time.perf_counter_ns() - start)
            access_times[i] = statistics.mean(times)

        sorted_times = sorted(access_times.items(), key=lambda x: x[1])

        return {
            "fastest_accesses": sorted_times[:10],
            "slowest_accesses": sorted_times[-10:],
            "cache_boundary_estimate": self._estimate_cache_boundary(access_times),
        }

    def _estimate_cache_boundary(self, access_times: dict[int, float]) -> int:
        sorted_items = sorted(access_times.items(), key=lambda x: x[0])
        max_diff = 0
        boundary = 0

        for i in range(1, len(sorted_items)):
            diff = sorted_items[i][1] - sorted_items[i - 1][1]
            if diff > max_diff:
                max_diff = diff
                boundary = sorted_items[i][0]

        return boundary


class ConstantTimeUtils:
    @staticmethod
    def compare_bytes(a: bytes, b: bytes) -> bool:
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= x ^ y
        return result == 0

    @staticmethod
    def compare_strings(a: str, b: str) -> bool:
        return ConstantTimeUtils.compare_bytes(a.encode(), b.encode())

    @staticmethod
    def compare_ints(a: int, b: int) -> bool:
        return (a ^ b) == 0

    @staticmethod
    def select_bit(bit: int, a: int, b: int) -> int:
        mask = -bit
        return (a & mask) | (b & ~mask)

    @staticmethod
    def conditional_copy(condition: bool, src: bytes, dst: bytearray, length: int):
        mask = -int(condition)
        for i in range(length):
            dst[i] = (src[i] & mask) | (dst[i] & ~mask)

    @staticmethod
    def verify_password_hash(password: bytes, hash_bytes: bytes, verify_func: Callable) -> bool:
        expected = verify_func(password)
        return ConstantTimeUtils.compare_bytes(expected, hash_bytes)
