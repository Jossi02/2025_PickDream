package com.example.pick_dream.repository

import android.util.Log
import com.google.firebase.FirebaseNetworkException
import com.google.firebase.firestore.FirebaseFirestoreException
import kotlinx.coroutines.TimeoutCancellationException
import java.io.IOException

sealed interface RepositoryResult<out T> {
    data class Success<T>(val data: T) : RepositoryResult<T>
    data class Error(val failure: RepositoryFailure) : RepositoryResult<Nothing>
}

enum class RepositoryErrorKind {
    AUTHENTICATION,
    PERMISSION,
    NETWORK,
    DATA,
    UNKNOWN
}

data class RepositoryFailure(
    val kind: RepositoryErrorKind,
    val operation: String,
    val cause: Throwable? = null
) {
    val userMessage: String
        get() = when (kind) {
            RepositoryErrorKind.AUTHENTICATION -> "로그인이 필요합니다."
            RepositoryErrorKind.PERMISSION -> "이 작업을 수행할 권한이 없습니다."
            RepositoryErrorKind.NETWORK -> "네트워크 연결을 확인한 후 다시 시도해 주세요."
            RepositoryErrorKind.DATA -> "저장된 정보를 처리할 수 없습니다."
            RepositoryErrorKind.UNKNOWN -> "요청 처리 중 오류가 발생했습니다. 다시 시도해 주세요."
        }
}

fun repositoryFailure(operation: String, throwable: Throwable): RepositoryFailure {
    val firestoreCode = (throwable as? FirebaseFirestoreException)?.code
    val kind = when {
        throwable is FirebaseNetworkException ||
            throwable is TimeoutCancellationException ||
            throwable is IOException -> RepositoryErrorKind.NETWORK
        firestoreCode == FirebaseFirestoreException.Code.PERMISSION_DENIED -> RepositoryErrorKind.PERMISSION
        firestoreCode == FirebaseFirestoreException.Code.UNAUTHENTICATED -> RepositoryErrorKind.AUTHENTICATION
        firestoreCode in setOf(
            FirebaseFirestoreException.Code.UNAVAILABLE,
            FirebaseFirestoreException.Code.DEADLINE_EXCEEDED,
            FirebaseFirestoreException.Code.ABORTED
        ) -> RepositoryErrorKind.NETWORK
        firestoreCode in setOf(
            FirebaseFirestoreException.Code.DATA_LOSS,
            FirebaseFirestoreException.Code.INVALID_ARGUMENT,
            FirebaseFirestoreException.Code.FAILED_PRECONDITION
        ) -> RepositoryErrorKind.DATA
        else -> RepositoryErrorKind.UNKNOWN
    }
    Log.e("Repository", "$operation failed (${kind.name})", throwable)
    return RepositoryFailure(kind, operation, throwable)
}

fun authenticationFailure(operation: String): RepositoryFailure =
    RepositoryFailure(RepositoryErrorKind.AUTHENTICATION, operation)

fun networkFailure(operation: String): RepositoryFailure =
    RepositoryFailure(RepositoryErrorKind.NETWORK, operation)

fun dataFailure(operation: String): RepositoryFailure =
    RepositoryFailure(RepositoryErrorKind.DATA, operation)
