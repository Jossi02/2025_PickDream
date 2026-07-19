package com.example.pick_dream.notification

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class ReservationAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val reservationId = intent.getStringExtra(
            PickDreamNotificationManager.EXTRA_RESERVATION_ID,
        ).orEmpty()
        if (reservationId.isBlank()) {
            // Alarms created by older app versions used mutable room/time fields. Ignoring them
            // prevents stale notifications after a reservation is changed or cancelled.
            return
        }
        if (!PickDreamNotificationManager.canShowNotifications(context)) return

        val notificationId = intent.getIntExtra(
            PickDreamNotificationManager.EXTRA_NOTIFICATION_ID,
            ReservationReminderPlanner.stableNotificationId(reservationId),
        )
        val record = ReservationReminderScheduler.takeForDelivery(
            context = context,
            reservationId = reservationId,
            notificationId = notificationId,
        ) ?: return

        PickDreamNotificationManager.showUsageReminderFromAlarm(
            context = context,
            notificationId = record.notificationId,
            title = record.title,
            body = record.body,
        )
    }
}
