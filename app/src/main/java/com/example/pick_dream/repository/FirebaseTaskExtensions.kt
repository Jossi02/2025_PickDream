package com.example.pick_dream.repository

import com.google.android.gms.tasks.Task
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout

private const val DEFAULT_FIREBASE_TIMEOUT_MILLIS = 10_000L

suspend fun <T> Task<T>.awaitWithTimeout(
    timeoutMillis: Long = DEFAULT_FIREBASE_TIMEOUT_MILLIS
): T = withTimeout(timeoutMillis) { await() }
