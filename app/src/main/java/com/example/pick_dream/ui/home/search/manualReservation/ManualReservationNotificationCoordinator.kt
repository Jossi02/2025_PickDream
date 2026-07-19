package com.example.pick_dream.ui.home.search.manualReservation

import android.content.Context
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.notification.PickDreamNotificationManager
import com.example.pick_dream.notification.ReservationReminderScheduler

object ManualReservationNotificationCoordinator {
    fun onReservationCreated(context: Context, reservation: Reservation) {
        PickDreamNotificationManager.showReservationComplete(context, reservation)
        ReservationReminderScheduler.upsert(context, reservation)
    }
}
