package com.example.pick_dream.ui.home.search.manualReservation

import com.example.pick_dream.model.Reservation
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.ui.home.reservation.ReservationRepository

object ManualReservationRepository {
    suspend fun getReservationsByRoom(roomId: String): RepositoryResult<List<Reservation>> =
        ReservationRepository.getReservationsByRoom(roomId)

    suspend fun createReservation(reservation: Reservation): RepositoryResult<Unit> =
        ReservationRepository.addReservation(reservation)
}
