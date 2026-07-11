package com.example.pick_dream.ui.home.search.manualReservation

import com.example.pick_dream.model.Reservation
import com.example.pick_dream.ui.home.reservation.ReservationRepository

object ManualReservationRepository {
    suspend fun getReservationsByRoom(roomId: String): List<Reservation> =
        ReservationRepository.getReservationsByRoom(roomId)

    suspend fun createReservation(reservation: Reservation): Boolean =
        ReservationRepository.addReservation(reservation)
}
