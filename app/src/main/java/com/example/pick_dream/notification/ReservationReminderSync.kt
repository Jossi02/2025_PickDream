package com.example.pick_dream.notification

import android.content.Context
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.repository.repositoryFailure
import com.example.pick_dream.ui.home.reservation.ReservationRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object ReservationReminderSync {
    suspend fun reconcileCurrentUser(context: Context): RepositoryResult<Unit> {
        if (!ReservationNotificationPreferences.isReservationUsageTimeEnabled(context)) {
            withContext(Dispatchers.IO) {
                ReservationReminderScheduler.cancelAll(context)
            }
            return RepositoryResult.Success(Unit)
        }

        return try {
            val studentId = UserRepository.getCurrentStudentId()
            if (studentId.isNullOrBlank()) {
                withContext(Dispatchers.IO) {
                    ReservationReminderScheduler.cancelAll(context)
                }
                RepositoryResult.Success(Unit)
            } else {
                when (val result = ReservationRepository.getReservationsByUser(studentId)) {
                    is RepositoryResult.Success -> {
                        withContext(Dispatchers.IO) {
                            ReservationReminderScheduler.reconcile(context, result.data)
                        }
                        RepositoryResult.Success(Unit)
                    }
                    is RepositoryResult.Error -> result
                }
            }
        } catch (error: Exception) {
            RepositoryResult.Error(repositoryFailure("예약 알림 동기화", error))
        }
    }
}
