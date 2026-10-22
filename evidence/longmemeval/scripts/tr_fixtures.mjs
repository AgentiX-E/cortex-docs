/**
 * Shared fixtures for iteration #145 (TR two-event temporal bug).
 *
 * Extracted from `verify_two_event_fixtures.mjs` so that both the pre-fix RED
 * verification and the post-fix GREEN verification read the SAME data, and so
 * that importing it has no side effects.
 *
 * Two-event fixtures are reconstructed from production data:
 *   answer = elapsed(A -> questionDate)  =>  A = questionDate - answer
 *   gold   = elapsed(A -> B)             =>  B = A + gold
 * Single-event fixtures are reconstructed from the GOLD, because one of them
 * fails for an unrelated reason (event extraction) and must pin the CORRECT
 * behaviour.
 */
export const TWO_EVENT = [
  {
    label: 'evelyn hugo',
    question:
      "How many days had passed since I finished reading 'The Seven Husbands of Evelyn Hugo' when I attended the book reading event at the local library, where the author of 'The Silent Patient' is discussing her latest thriller novel?",
    questionDate: '2023/02/10 (Fri) 18:44',
    events: [
      { name: "finished reading 'The Seven Husbands of Evelyn Hugo'", date: '2022/12/28' },
      { name: 'attended the book reading event at the local library', date: '2023/01/15' },
    ],
    observed: '44',
    gold: '18',
  },
  {
    label: 'ukulele',
    question:
      'How many days had passed since I started taking ukulele lessons when I decided to take my acoustic guitar to the guitar tech for servicing?',
    questionDate: '2023/04/01 (Sat) 00:42',
    events: [
      { name: 'started taking ukulele lessons', date: '2023/02/01' },
      { name: 'took my acoustic guitar to the guitar tech', date: '2023/02/25' },
    ],
    observed: '59',
    gold: '24',
  },
  {
    label: 'flu',
    question:
      'How many weeks had passed since I recovered from the flu when I went on my 10th jog outdoors?',
    questionDate: '2023/10/15 (Sun) 17:53',
    events: [
      { name: 'recovered from the flu', date: '2023/01/22' },
      { name: 'went on my 10th jog outdoors', date: '2023/05/07' },
    ],
    observed: '38',
    gold: '15',
  },
  {
    label: 'website',
    question:
      'How many days ago did I launch my website when I signed a contract with my first client?',
    questionDate: '2023/03/25 (Sat) 19:57',
    events: [
      { name: 'launched my website', date: '2023/03/01' },
      { name: 'signed a contract with my first client', date: '2023/03/20' },
    ],
    observed: '24',
    gold: '19',
  },
  {
    label: 'adidas',
    question:
      'How many days had passed since I bought my Adidas running shoes when I realized one of the shoelaces on my old Converse sneakers had broken?',
    questionDate: '2023/02/03 (Fri) 17:43',
    events: [
      { name: 'bought my Adidas running shoes', date: '2023/01/10' },
      { name: 'realized a shoelace on my Converse had broken', date: '2023/01/24' },
    ],
    observed: '24',
    gold: '14',
  },
];

/** The 19 single-event relative questions that MUST NOT change behaviour. */
export const SINGLE_EVENT = [
  ['How many weeks ago did I meet up with my aunt and receive the crystal chandelier?', '2023/04/01 (Sat) 08:09', '2023/03/04', '4'],
  ['How many months have passed since I participated in two charity events in a row, on consecutive days?', '2023/04/18 (Tue) 03:31', '2023/02/18', '2'],
  ['How many months have passed since I last visited a museum with a friend?', '2023/03/25 (Sat) 17:18', '2022/10/25', '5'],
  ['How many weeks ago did I attend the friends and family sale at Nordstrom?', '2022/12/01 (Thu) 21:26', '2022/11/17', '2'],
  ['How many days ago did I attend the Maundy Thursday service at the Episcopal Church?', '2023/04/10 (Mon) 10:28', '2023/04/06', '4'],
  ["How many weeks ago did I start using the cashback app 'Ibotta'?", '2023/05/06 (Sat) 09:18', '2023/04/15', '3'],
  ['How many months ago did I attend the Seattle International Film Festival?', '2021/10/02 (Sat) 03:56', '2021/06/02', '4'],
  ['How many days ago did I buy a smoker?', '2023/03/25 (Sat) 02:46', '2023/03/15', '10'],
  ['How many days ago did I meet Emma?', '2023/04/20 (Thu) 10:12', '2023/04/11', '9'],
  ['How many days ago did I attend a networking event?', '2022/04/04 (Mon) 21:03', '2022/03/09', '26'],
  ['How many weeks ago did I attend a bird watching workshop at the local Audubon society?', '2023/05/01 (Mon) 23:16', '2023/04/03', '4'],
  ['How many months ago did I attend the photography workshop?', '2024/02/01 (Thu) 18:06', '2023/11/01', '3'],
  ['How many days ago did I watch the Super Bowl?', '2023/03/01 (Wed) 19:28', '2023/02/12', '17'],
  ['How many days ago did I go on a whitewater rafting trip in the Oregon mountains?', '2023/06/20 (Tue) 16:30', '2023/06/17', '3'],
  ['How many days ago did I harvest my first batch of fresh herbs from the herb garden kit?', '2023/04/18 (Tue) 01:48', '2023/04/15', '3'],
  ["How many weeks ago did I attend the 'Summer Nights' festival at Universal Studios Hollywood?", '2023/08/05 (Sat) 08:21', '2023/07/15', '3'],
  ['How many days ago did I participate in the 5K charity run?', '2023/03/26 (Sun) 04:13', '2023/03/19', '7'],
  ['How many days ago did I read the March 15th issue of The New Yorker?', '2023/04/01 (Sat) 08:36', '2023/03/20', '12'],
  ['How many months ago did I book the Airbnb in San Francisco?', '2023/05/21 (Sun) 10:30', '2022/12/21', '5'],
];
