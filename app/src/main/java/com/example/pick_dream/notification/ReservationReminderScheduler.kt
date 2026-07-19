package com.example.pick_dream.notification

import android.content.Context
import com.example.pick_dream.model.Reservation

object ReservationReminderScheduler {
    @Synchronized
    fun upsert(context: Context, reservation: Reservation): ReservationReminderRecord? =
        reconciler(context).upsert(
            reservation,
            enabled = ReservationNotificationPreferences.isReservationUsageTimeEnabled(context),
        )

    @Synchronized
    fun reconcile(context: Context, reservations: List<Reservation>) {
        reconciler(context).reconcile(
            reservations,
            enabled = ReservationNotificationPreferences.isReservationUsageTimeEnabled(context),
        )
    }

    @Synchronized
    fun cancel(context: Context, reservationId: String) {
        if (reservationId.isNotBlank()) {
            reconciler(context).cancel(reservationId)
        }
    }

    @Synchronized
    fun cancelAll(context: Context) {
        reconciler(context).reconcile(emptyList(), enabled = false)
    }

    @Synchronized
    fun restorePersisted(context: Context) {
        if (!ReservationNotificationPreferences.isReservationUsageTimeEnabled(context)) {
            reconciler(context).reconcile(emptyList(), enabled = false)
        } else if (PickDreamNotificationManager.canShowNotifications(context)) {
            reconciler(context).restorePersisted()
        }
    }

    @Synchronized
    fun takeForDelivery(
        context: Context,
        reservationId: String,
        notificationId: Int,
    ): ReservationReminderRecord? {
        if (!ReservationNotificationPreferences.isReservationUsageTimeEnabled(context)) {
            cancel(context, reservationId)
            return null
        }
        return reconciler(context).takeForDelivery(reservationId, notificationId)
    }

    private fun reconciler(context: Context): ReservationReminderReconciler =
        ReservationReminderReconciler(
            store = SharedPreferencesReservationReminderStore(context),
            gateway = AndroidReservationReminderAlarmGateway(context),
        )
}
