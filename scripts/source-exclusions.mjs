// Exact provider race/event IDs only: event IDs also cover later dated editions.
export function sourceExcluded(race,exclusions){
  return [race.id,race.eventId].some(id=>id&&Object.hasOwn(exclusions,id));
}
