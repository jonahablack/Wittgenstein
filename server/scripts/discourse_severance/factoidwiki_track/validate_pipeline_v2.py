"""Validate pipeline_part0d_v2.evaluate_v2 on a combined 10-case set:
  - calibration anchors items 3, 9, 18 (marker-absent, real juxtaposition-
    only Concessions -- tests the new NLI relation-entailment branch)
  - calibration anchor item 20 (leading-pronoun anaphora in ground truth
    -- tests resolve_leading_pronoun)
  - calibration anchor item 24 (NuggetIndex, correctly severed by the
    human rater with precise reasoning -- negative control, must stay
    severed under the new relation-entailment branch, not get swept up
    by loosening the marker requirement)
  - pool 3278/arm_4, 4200/arm_4 (misattachment negative controls --
    marker present, must still route to the parser branch and stay
    severed, unaffected by the marker-absent-branch redesign)
  - pool 4117/arm_2 (reversal negative control), 4117/arm_3 (normal
    positive control), 4117/arm_4 (definite-description anaphora in the
    parser-resolved clause -- tests resolve_definite_description)
"""

import json
import sys

sys.path.insert(0, ".")
from pipeline_part0d_v2 import evaluate_v2  # noqa: E402

CASES = [
    {"id": "item3-Destination_Moon", "expected": True, "source": "calibration-anchor",
     "relation_type": "Concession",
     "nucleus": "the other four each won an Academy Award for Best Visual Effects",
     "satellite": "Although Conquest of Space was a commercial failure that set back Pal's career",
     "connective": "Although",
     "paragraph": "One of the earlier and most important films of the era was the widely publicized Destination Moon, released in 1950. It follows a nuclear-powered rocketship carrying four men to the moon, against a background of competition against the Soviets. With a script co-written by Robert A. Heinlein and astronomical sets by renowned space artist Chesley Bonestell, the film was a commercial and artistic success, and it brought about more studio financing of science fiction films. The producer of Destination Moon was notably George Pal who also helped create When Worlds Collide, The Time Machine, The War of the Worlds, and the pseudo-documentary of manned space exploration Conquest of Space. Although Conquest of Space was a commercial failure that set back Pal's career, the other four each won an Academy Award for Best Visual Effects, which demonstrated the increased technical excellence and critical recognition of the genre.",
     "propositions": ["One of the earlier and most important films of the era was the widely publicized Destination Moon.",
                       "Destination Moon was released in 1950.", "Destination Moon follows a nuclear-powered rocketship carrying four men to the moon.",
                       "Destination Moon is set against a background of competition against the Soviets.",
                       "The script of Destination Moon was co-written by Robert A. Heinlein.",
                       "The astronomical sets of Destination Moon were created by renowned space artist Chesley Bonestell.",
                       "Destination Moon was a commercial success.", "Destination Moon was an artistic success.",
                       "Destination Moon brought about more studio financing of science fiction films.",
                       "The producer of Destination Moon was George Pal.", "George Pal helped create When Worlds Collide.",
                       "George Pal helped create The Time Machine.", "George Pal helped create The War of the Worlds.",
                       "George Pal helped create the pseudo-documentary of manned space exploration Conquest of Space.",
                       "Conquest of Space was a commercial failure.", "Conquest of Space set back George Pal's career.",
                       "When Worlds Collide won an Academy Award for Best Visual Effects.",
                       "The Time Machine won an Academy Award for Best Visual Effects.",
                       "The War of the Worlds won an Academy Award for Best Visual Effects.",
                       "Conquest of Space did not win an Academy Award for Best Visual Effects.",
                       "The other four films each won an Academy Award for Best Visual Effects.",
                       "The success of the other four films demonstrated the increased technical excellence of the genre.",
                       "The success of the other four films demonstrated the critical recognition of the genre."]},
    {"id": "item9-Bergson", "expected": True, "source": "calibration-anchor",
     "relation_type": "Concession",
     "nucleus": "many religious leaders, particularly the more liberal-minded theologians of all creeds, e.g., the Modernists and Neo-Catholic Party in his own country, showed a keen interest in his writings, and many of them found encouragement and stimulus in his work.",
     "satellite": "The Roman Catholic Church, however, banned Bergson's three books on the charge of pantheism (that is, of conceiving of God as immanent to his Creation and of being himself created in the process of the Creation).",
     "connective": "however",
     "paragraph": "While social revolutionaries endeavoured to make the most out of Bergson, many religious leaders, particularly the more liberal-minded theologians of all creeds, e.g., the Modernists and Neo-Catholic Party in his own country, showed a keen interest in his writings, and many of them found encouragement and stimulus in his work. The Roman Catholic Church, however, banned Bergson's three books on the charge of pantheism (that is, of conceiving of God as immanent to his Creation and of being himself created in the process of the Creation). They were placed on the Index of prohibited books (Decree of 1 June 1914).",
     "propositions": ["Bergson's writings garnered interest from many liberal-minded theologians, including the Modernists and Neo-Catholic Party in his country, who found encouragement in his work.",
                       "The Roman Catholic Church banned Bergson's three books due to the charge of pantheism, which involves the conception of God as immanent to Creation.",
                       "Bergson's three books were placed on the Index of prohibited books following the Decree of 1 June 1914."]},
    {"id": "item18-California_freeway", "expected": True, "source": "calibration-anchor",
     "relation_type": "Concession",
     "nucleus": "the state is not immune to freeway revolts",
     "satellite": "However, the state is not immune to freeway revolts, such as those that have prevented a freeway in San Francisco between the Golden Gate Bridge and the San Francisco-Oakland Bay Bridge, and an expansion of I-710 through South Pasadena.",
     "connective": "However",
     "paragraph": "The state's freeway network has expanded ever since the Arroyo Seco Parkway, the first freeway in the Western United States, connecting Los Angeles and Pasadena, opened in 1940. However, the state is not immune to freeway revolts, such as those that have prevented a freeway in San Francisco between the Golden Gate Bridge and the San Francisco-Oakland Bay Bridge, and an expansion of I-710 through South Pasadena.",
     "propositions": ["The Arroyo Seco Parkway, which opened in 1940, is the first freeway in the Western United States, connecting Los Angeles and Pasadena.",
                       "The state's freeway network has expanded since the opening of the Arroyo Seco Parkway in 1940.",
                       "The state has experienced freeway revolts that have prevented the construction of a freeway in San Francisco between the Golden Gate Bridge and the San Francisco-Oakland Bay Bridge.",
                       "Freeway revolts have also prevented the expansion of I-710 through South Pasadena."]},
    {"id": "item20-Eritrea", "expected": True, "source": "calibration-anchor",
     "relation_type": "Concession",
     "nucleus": "it was nonetheless under the scrutiny and control of the Italians.",
     "satellite": "Though in Eritrea Football Federation was formed in 1936, during the Italian colonialism, allowing indigenous teams to be established and run their own tournaments,",
     "connective": "Though",
     "paragraph": "Though in Eritrea Football Federation was formed in 1936, during the Italian colonialism, allowing indigenous teams to be established and run their own tournaments, it was nonetheless under the scrutiny and control of the Italians.",
     "propositions": ["The Eritrea Football Federation was formed in 1936 during Italian colonialism.",
                       "Indigenous teams were allowed to be established and run their own tournaments during Italian colonialism.",
                       "The Football Federation was under the scrutiny and control of the Italians.",
                       "The free and independent Football Federation was formed during the period of federation (1952-1962).",
                       "Ethiopia illegally annexed Eritrea.",
                       "The Football Federation had to go back to being under heavy control after the annexation."]},
    {"id": "item24-Jormungandr", "expected": False, "source": "calibration-anchor",
     "relation_type": "Condition",
     "nucleus": "he would have altered the boundaries of the universe.",
     "satellite": "If Thor had managed to lift the cat completely from the ground,",
     "connective": "If",
     "paragraph": "In one story, Thor encounters the giant king Utgarda-Loki and has to perform deeds for him, one of which is a challenge of Thor's strength. Utgarda-Loki goads Thor into attempting to lift the World Serpent, disguised by magic as a huge cat. Thor grabs the cat around its midsection but manages to raise the cat only high enough for one of its paws to leave the floor. Utgarda-Loki later explains his deception and that Thor's lifting the cat was an impressive deed, as he stretched the serpent so that it almost reached the sky. Many watching became fearful when they saw one paw lift off the ground. If Thor had managed to lift the cat completely from the ground, he would have altered the boundaries of the universe.",
     "propositions": ["Thor encounters Utgarda-Loki", "Thor attempts World Serpent", "Utgarda-Loki goads Thor",
                       "Thor grabs cat", "Thor manages one of its paws", "Utgarda-Loki explains his deception",
                       "Thor lifting cat", "Thor stretched serpent", "Many became fearful",
                       "Thor would have altered boundaries of the universe"]},
    {"id": "3278-misattach", "expected": False, "source": "hard-case-negative-control",
     "relation_type": "Concession",
     "nucleus": "he never showed any personal dislike of York in the 1450s, and that his personal motivation throughout the decade was loyalty to the Crown and keeping the peace between his peers.",
     "satellite": "B. J. Harris noted that, although he died a staunch Lancastrian,", "connective": "although",
     "paragraph": "B. J. Harris noted that, although he died a staunch Lancastrian, he never showed any personal dislike of York in the 1450s, and that his personal motivation throughout the decade was loyalty to the Crown and keeping the peace between his peers.",
     "propositions": ["Humphrey Stafford was the 1st Duke of Buckingham.", "B. J. Harris is a historian.",
                       "Humphrey Stafford died a staunch Lancastrian.",
                       "Humphrey Stafford never showed any personal dislike of York in the 1450s.",
                       "The paragraph discusses B. J. Harris's observations about Humphrey Stafford, highlighting his loyalty to the Crown and efforts to maintain peace among his peers, despite his involvement in the political conflicts of the 1450s. Humphrey Stafford's personal motivation was loyalty to the Crown and keeping the peace between his peers.",
                       "Rawcliffe is another historian.", "Rawcliffe suggested that Humphrey Stafford lacked the necessary qualities to become a great statesman or leader.",
                       "Humphrey Stafford was an unimaginative and unlikeable man according to Rawcliffe.",
                       "Humphrey Stafford had a reputation as a harsh taskmaster on his estates.",
                       "Humphrey Stafford displayed offensive behavior towards Joan of Arc.",
                       "Rawcliffe says that Humphrey Stafford's political judgement could be clouded by his attitude.",
                       "Humphrey Stafford had an ungovernable temper according to Rawcliffe."]},
    {"id": "4200-misattach", "expected": False, "source": "hard-case-negative-control",
     "relation_type": "Concession",
     "nucleus": "the Pittsburgh Penguins lent him to Team Canada.",
     "satellite": "Although Fleury was playing in the NHL the next year leading up to the tournament,", "connective": "Although",
     "paragraph": "Although Fleury was playing in the NHL the next year leading up to the tournament, the Pittsburgh Penguins lent him to Team Canada.",
     "propositions": ["Marc-André Fleury was playing in the NHL the next year leading up to the tournament.",
                       "The paragraph discusses Marc-André Fleury's participation in a high-profile tournament with Team Canada, highlighting that despite his desire to stay with the Pittsburgh Penguins, the team lent him to represent Canada for his development. The Pittsburgh Penguins lent Marc-André Fleury to Team Canada.",
                       "Marc-André Fleury expressed a desire to remain with his NHL club.",
                       "Penguins management decided the high-profile tournament would be good for Marc-André Fleury's development.",
                       "Marc-André Fleury led Team Canada to the gold medal game for the second consecutive year.",
                       "Marc-André Fleury made a costly mistake that lost his team the championship."]},
    {"id": "4117-arm2-reversed", "expected": False, "source": "hard-case-negative-control",
     "relation_type": "Concession", "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
     "satellite": "although French remained the only official language in Belgium", "connective": "although",
     "paragraph": "Certain events led to a silent uprising in Flanders against French-speaking domination. Dutch was not allowed to be used for official purposes in Flanders until 1878. Although Dutch was allowed for official purposes in Flanders, French remained the only official language in Belgium.",
     "propositions": ["Certain events led to a silent uprising in Flanders against French-speaking domination.",
                       "Dutch was not allowed to be used for official purposes in Flanders until 1878.",
                       "Although Dutch was allowed for official purposes in Flanders, French remained the only official language in Belgium."]},
    {"id": "4117-arm3-normal", "expected": True, "source": "hard-case-positive-control",
     "relation_type": "Concession", "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
     "satellite": "although French remained the only official language in Belgium", "connective": "although",
     "paragraph": "These events led to a silent uprising in Flanders against French-speaking domination. Dutch was allowed to be used for official purposes in Flanders in 1878, although French remained the only official language in Belgium. Language legislation in Belgium is related to the use of Dutch for official purposes in Flanders. French remained the only official language in Belgium.",
     "propositions": ["These events led to a silent uprising in Flanders against French-speaking domination.",
                       "Dutch was allowed to be used for official purposes in Flanders in 1878, although French remained the only official language in Belgium.",
                       "Language legislation in Belgium is related to the use of Dutch for official purposes in Flanders.",
                       "French remained the only official language in Belgium."]},
    {"id": "4117-arm4-anaphora", "expected": True, "source": "hard-case-anaphora",
     "relation_type": "Concession", "nucleus": "Dutch was allowed to be used for official purposes in Flanders",
     "satellite": "although French remained the only official language in Belgium", "connective": "although",
     "paragraph": "These events led to a silent uprising in Flanders against French-speaking domination. The paragraph discusses the historical context of language dominance in Belgium, highlighting the silent uprising in Flanders against French-speaking control and the eventual recognition of Dutch for official use in 1878, despite French remaining the sole official language in the country. Dutch was allowed to be used for official purposes in Flanders in 1878. Language legislation in Belgium is related to the use of Dutch for official purposes in Flanders. French remained the only official language in Belgium.",
     "propositions": ["These events led to a silent uprising in Flanders against French-speaking domination.",
                       "The paragraph discusses the historical context of language dominance in Belgium, highlighting the silent uprising in Flanders against French-speaking control and the eventual recognition of Dutch for official use in 1878, despite French remaining the sole official language in the country. Dutch was allowed to be used for official purposes in Flanders in 1878.",
                       "Language legislation in Belgium is related to the use of Dutch for official purposes in Flanders.",
                       "French remained the only official language in Belgium."]},

    # --- newly-confirmed scale-up failures, must now pass -------------
    {"id": "pool1943-Bug1-unresolved-already-works", "expected": True, "source": "scale-up-bug-fix",
     "relation_type": "Condition", "nucleus": "it costs double.",
     "satellite": "if a passenger passes the zone limit,", "connective": "if",
     "paragraph": "ZTM tickets are valid on city and suburban bus lines, as well as trams, Metro, and SKM. A given ticket costs the same price within one zone. If a passenger passes the zone limit, the ticket costs double.",
     "propositions": ["ZTM tickets are valid on city and suburban bus lines.", "ZTM tickets are valid on trams.",
                       "ZTM tickets are valid on Metro.", "ZTM tickets are valid on SKM.",
                       "A given ticket costs the same price within one zone.",
                       "If a passenger passes the zone limit, the ticket costs double.",
                       "Tickets are best bought at newsagents."]},
    {"id": "pool1986-Bug2-compound-satellite-window", "expected": True, "source": "scale-up-bug-fix",
     "relation_type": "Condition",
     "nucleus": "the shift to alternative technologies will only be successful",
     "satellite": "if the resultant built environment is attractive to a local culture and can be maintained and adapted as necessary over multiple generations",
     "connective": "if",
     "paragraph": "Practical ecovillage builders like Living Villages maintain that the shift to alternative technologies will only be successful if the resultant built environment is attractive to a local culture. The built environment should be able to be maintained and adapted as necessary over multiple generations.",
     "propositions": ["Practical ecovillage builders like Living Villages exist.",
                       "Living Villages maintain that the shift to alternative technologies will only be successful if the resultant built environment is attractive to a local culture.",
                       "The built environment should be able to be maintained and adapted as necessary over multiple generations."]},

    # --- fallback-untriggered coverage: unresolved hypothesis already
    # entails correctly; resolution must not run or must not override --
    {"id": "pool1814-untriggered-fallback", "expected": True, "source": "fallback-untriggered",
     "relation_type": "Condition", "nucleus": "this would also support an Italian origin.",
     "satellite": "If true,", "connective": "If",
     "paragraph": "Some researchers of the work argue for an Italian origin, noting phrases in Barnabas which are very similar to phrases used by Dante and suggesting that the author of Barnabas borrowed from Dante's works. If true, this would also support an Italian origin for the Gospel of Barnabas.",
     "propositions": ["Some researchers argue for an Italian origin of the Gospel of Barnabas.",
                       "Phrases in Barnabas are very similar to phrases used by Dante.",
                       "The author of Barnabas may have borrowed from Dante's works.",
                       "If true, this would also support an Italian origin for the Gospel of Barnabas."]},
    {"id": "pool2386-untriggered-fallback", "expected": True, "source": "fallback-untriggered",
     "relation_type": "Condition",
     "nucleus": "it is likely, the commission will find the undertaking to be dominant.",
     "satellite": "Following Paragraph 13 of the commission's guidance, where the three conditions are satisfied,",
     "connective": "where",
     "paragraph": "Following Paragraph 13 of the commission's guidance, where the three conditions are satisfied, it is likely, the commission will find the undertaking to be dominant.",
     "propositions": ["Article 102 is part of the Treaty on the Functioning of the European Union.",
                       "Paragraph 13 of the commission's guidance discusses the conditions for finding an undertaking to be dominant.",
                       "If the three conditions are satisfied, the commission is likely to find the undertaking to be dominant.",
                       "Dominance in itself is not illegal, according to Paragraph 1 of the commission's guidance."]},

    # --- Tier 1, gaps 6/7: multi-word connectives (real corpus cases,
    # 3 of the 7 phrases; "even if"/"provided that"/"as long as" have no
    # clean on-target real occurrence anywhere in the corpus after a
    # full search across all four govern logs and all three Exp3
    # reports -- constructed as synthetic cases below instead, flagged
    # explicitly rather than stretching a real but off-target match ---
    {"id": "pool1902-ownbaseline-even_though", "expected": True, "source": "multiword-real-last-token",
     "relation_type": "Concession", "nucleus": "the barons swore allegiance to him",
     "satellite": "even though he did not return for two years", "connective": "even though",
     "paragraph": "Savage retribution was inflicted upon the rebels, and authority restored to Henry. With the realm now peaceful, Edward left England to join Louis IX on the Ninth Crusade. The barons swore allegiance to Edward even though he did not return for two years.",
     "propositions": ["Savage retribution was inflicted upon the rebels.", "Authority was restored to Henry.",
                       "Edward left England to join Louis IX on the Ninth Crusade.",
                       "The barons swore allegiance to Edward even though he did not return for two years."]},
    {"id": "pool3238-ownbaseline-in_spite_of", "expected": True, "source": "multiword-real-first-token",
     "relation_type": "Concession",
     "nucleus": "the next day she was summoned by Gerald Gauthier, director of the Press Agency at Opera Mundi.",
     "satellite": "In spite of floundering on the second-to-last question,", "connective": "In spite of",
     "paragraph": "In 1959 she participated in the popular television quiz show Le Gros Lot. In spite of floundering on the second-to-last question, the next day she was summoned by Gerald Gauthier, director of the Press Agency at Opera Mundi.",
     "propositions": ["In 1959 she participated in the popular television quiz show Le Gros Lot.",
                       "The topic was the Italian Renaissance.", "The subject was Catherina Sforza.",
                       "In spite of floundering on the second-to-last question, the next day she was summoned by Gerald Gauthier, director of the Press Agency at Opera Mundi."]},
    {"id": "pool3645-atomicrag-in_the_event_of", "expected": True, "source": "multiword-real-first-token-plus-compound",
     "relation_type": "Condition",
     "nucleus": "Kurzweil plans to be perfused with cryoprotectants, vitrified in liquid nitrogen, and stored at an Alcor facility in the hope that future medical technology will be able to repair his tissues and revive him.",
     "satellite": "In the event of his declared death", "connective": "In the event of",
     "paragraph": "Kurzweil has joined the Alcor Life Extension Foundation, which is a cryonics company. In the event of his declared death, Kurzweil plans to be perfused with cryoprotectants and vitrified in liquid nitrogen at an Alcor facility. Kurzweil hopes that future medical technology will be able to repair his tissues and revive him after being stored at the Alcor facility.",
     "propositions": ["Kurzweil has joined the Alcor Life Extension Foundation, which is a cryonics company, to pursue life extension through advanced medical technology.",
                       "In the event of his declared death, Kurzweil plans to be perfused with cryoprotectants and vitrified in liquid nitrogen at an Alcor facility.",
                       "Kurzweil hopes that future medical technology will be able to repair his tissues and revive him after being stored at the Alcor facility."]},
    {"id": "synthetic-only_if-already-covered-note", "expected": True, "source": "multiword-real-last-token",
     "relation_type": "Condition",
     "nucleus": "the shift to alternative technologies will only be successful",
     "satellite": "if the resultant built environment is attractive to a local culture and can be maintained and adapted as necessary over multiple generations",
     "connective": "if",
     "paragraph": "Practical ecovillage builders like Living Villages maintain that the shift to alternative technologies will only be successful if the resultant built environment is attractive to a local culture. The built environment should be able to be maintained and adapted as necessary over multiple generations.",
     "propositions": ["Living Villages, a practical ecovillage builder, asserts that the shift to alternative technologies will be successful only if the built environment is attractive to local culture.",
                       "Living Villages emphasizes the importance of maintaining and adapting the built environment as necessary over multiple generations."]},
    {"id": "synthetic-provided_that", "expected": True, "source": "multiword-synthetic-no-real-example-found",
     "relation_type": "Condition", "nucleus": "the loan will be approved",
     "satellite": "provided that the applicant meets the income requirements", "connective": "provided that",
     "paragraph": "The loan application was submitted last week. The loan will be approved provided that the applicant meets the income requirements. The bank reviews applications within ten business days.",
     "propositions": ["The loan application was submitted last week.",
                       "The loan will be approved provided that the applicant meets the income requirements.",
                       "The bank reviews applications within ten business days."]},
    {"id": "synthetic-as_long_as", "expected": True, "source": "multiword-synthetic-no-real-example-found",
     "relation_type": "Condition", "nucleus": "the warranty remains valid",
     "satellite": "as long as the device is used according to the instructions", "connective": "as long as",
     "paragraph": "The device comes with a two-year warranty. The warranty remains valid as long as the device is used according to the instructions. Customers can register their warranty online.",
     "propositions": ["The device comes with a two-year warranty.",
                       "The warranty remains valid as long as the device is used according to the instructions.",
                       "Customers can register their warranty online."]},
    {"id": "synthetic-even_if", "expected": True, "source": "multiword-synthetic-no-real-example-found",
     "relation_type": "Condition", "nucleus": "it would enter the Unhealthy range",
     "satellite": "even if it were to increase by only 1", "connective": "even if",
     "paragraph": "The API reading was at the top of the Moderate range. Even if it were to increase by only 1, it would enter the Unhealthy range. The reading was recorded at 5am.",
     "propositions": ["The API reading was at the top of the Moderate range.",
                       "Even if it were to increase by only 1, it would enter the Unhealthy range.",
                       "The reading was recorded at 5am."]},

    # --- Tier 1, gap 11: definite-description fallback GENUINELY
    # triggered and needed. 4117-arm4 no longer qualifies (now rescued
    # by the compound-window branch instead). Extensive real-corpus
    # search (all four govern logs, all three Exp3 reports, every
    # generic-referent noun) found no clean on-target real case -- every
    # match either belonged to a different relation in the same record
    # (false positive) or was itself compound/rescued. Constructed
    # minimal synthetic case instead, explicitly flagged. Uses "Boston"
    # rather than a lower-profile place name because spaCy's NER
    # (en_core_web_sm) did not reliably tag less common names as GPE in
    # a short context -- checked directly, not assumed.
    {"id": "synthetic-gap11-definite-description-needed", "expected": True,
     "source": "gap11-synthetic-no-real-example-found",
     "relation_type": "Concession", "nucleus": "the festival continued as planned.",
     "satellite": "despite flooding in Boston.", "connective": "despite",
     "paragraph": "Boston experienced flooding that week. Despite the flooding in the city, the festival continued as planned. Attendance was lower than in previous years.",
     "propositions": ["Boston experienced flooding that week.",
                       "Despite the flooding in the city, the festival continued as planned.",
                       "Attendance was lower than in previous years."]},

    # --- Tier 2: gaps 2, 3, 5 ported forward from the prior
    # (pipeline_part0d.py) architecture's own validation set. These
    # passed once already under that earlier design; re-tested here
    # against the current pipeline to confirm the port itself doesn't
    # surface a fourth mechanical bug (it doesn't -- all pass as-is). ---
    {"id": "pool2004-arm2-gap3-however-cross-prop", "expected": True, "source": "gap3-ported-positional-fallback",
     "relation_type": "Concession",
     "nucleus": "The emblem of 2010 Winter Olympics, \"Ilanaaq the Inukshuk\", was picked through an open contest.",
     "satellite": "However, it met criticism from some aboriginal groups over its design.", "connective": "However",
     "paragraph": "The emblem of the 2010 Winter Olympics, \"Ilanaaq the Inukshuk\", was picked through an open contest. However, it met criticism from some aboriginal groups over its design.",
     "propositions": ["The emblem of the 2010 Winter Olympics, \"Ilanaaq the Inukshuk\", was picked through an open contest.",
                       "However, it met criticism from some aboriginal groups over its design.",
                       "As a result, the mascot artist was selected through a competition."]},
    {"id": "pool2004-arm3-gap3-however-same-prop", "expected": True, "source": "gap3-ported-positional-fallback",
     "relation_type": "Concession",
     "nucleus": "The emblem of 2010 Winter Olympics, \"Ilanaaq the Inukshuk\", was picked through an open contest.",
     "satellite": "However, it met criticism from some aboriginal groups over its design.", "connective": "However",
     "paragraph": "The emblem of 2010 Winter Olympics was 'Ilanaaq the Inukshuk', however, it met criticism from some aboriginal groups over its design.",
     "propositions": ["The emblem of 2010 Winter Olympics was 'Ilanaaq the Inukshuk', however, it met criticism from some aboriginal groups over its design.",
                       "Ilanaaq the Inukshuk was picked through an open contest.",
                       "Ilanaaq the Inukshuk met criticism from some aboriginal groups over its design.",
                       "The mascot artist for the 2010 Winter Olympics was selected through a competition."]},
    {"id": "pool2659-arm4-gap3-but-synonym", "expected": True, "source": "gap3-ported-positional-fallback",
     "relation_type": "Concession",
     "nucleus": "there are also rural zones such as the Bosque La Primavera, El Diente and Ixtepete.",
     "satellite": "Although the area is mostly urban", "connective": "Although",
     "paragraph": "The Guadalajara area's attractions are mainly in the city itself and Zapopan, Tlaquepaque, and Tonala. Although the area is mostly urban, there are also rural zones such as the Bosque La Primavera, El Diente and Ixtepete.",
     "propositions": ["The Guadalajara area's attractions are mainly in the city itself and Zapopan, Tlaquepaque, and Tonala.",
                       "The area is mostly urban.", "There are also rural zones in the Guadalajara area.",
                       "The Guadalajara area's attractions are principally in the city itself and nearby urban areas, but it also includes rural zones such as Bosque La Primavera, El Diente, and Ixtepete. Rural zones in the Guadalajara area include Bosque La Primavera, El Diente, and Ixtepete."]},
    {"id": "pool2272-arm2-gap5-marker-on-nucleus-side", "expected": True, "source": "gap5-ported-marker-on-nucleus",
     "relation_type": "Concession",
     "nucleus": "King announced that he had changed his mind, and on National Signing Day a month later, signed to play for the Tigers of Auburn University beginning in the 2013 FBS season.",
     "satellite": "In July 2012, King verbally committed to transfer to the University of South Alabama and to play for the Jaguars football team.",
     "connective": "However",
     "paragraph": "In July 2012, King verbally committed to transfer to the University of South Alabama and to play for the Jaguars football team. However, in January 2013, King announced that he had changed his mind about this commitment. On National Signing Day a month later, King signed to play for the Tigers of Auburn University beginning in the 2013 FBS season.",
     "propositions": ["In July 2012, King verbally committed to transfer to the University of South Alabama and to play for the Jaguars football team.",
                       "However, in January 2013, King announced that he had changed his mind about this commitment.",
                       "On National Signing Day a month later, King signed to play for the Tigers of Auburn University beginning in the 2013 FBS season."]},
    {"id": "pool2894-gap2-despite-same-proposition", "expected": True, "source": "gap2-real-same-proposition-despite",
     "relation_type": "Concession",
     "nucleus": "hardly anyone actually rode in the wagons; it was too dusty, too rough, and too hard on the livestock.",
     "satellite": "Despite modern depictions,", "connective": "Despite",
     "paragraph": "The wagons on the Oregon Trail had no springs. The ride along the Oregon Trail was very rough. Despite modern depictions, hardly anyone actually rode in the wagons. Riding in the wagons was too dusty, too rough, and too hard on the livestock.",
     "propositions": ["The wagons on the Oregon Trail had no springs.", "The ride along the Oregon Trail was very rough.",
                       "Despite modern depictions, hardly anyone actually rode in the wagons.",
                       "Riding in the wagons was too dusty, too rough, and too hard on the livestock."]},
]


def main():
    results = []
    for c in CASES:
        out = evaluate_v2(c["propositions"], c["nucleus"], c["satellite"], c["connective"],
                           c["relation_type"], source_paragraph=c["paragraph"])
        correct = out["preserved"] == c["expected"]
        results.append({"id": c["id"], "source": c["source"], "expected": c["expected"], **out, "correct": correct})
        print(f"[{'PASS' if correct else 'FAIL'}] {c['id']} ({c['source']}): expected={c['expected']} "
              f"actual={out['preserved']}  reason={out['reason']}")
        if "resolved_clause" in out:
            print(f"    clause: {out['resolved_clause']!r} -> resolved: {out.get('clause_resolved')!r}")
        if "premise_used" in out:
            print(f"    premise: {out['premise_used'][:150]!r}")
        if "relation_scores" in out:
            print(f"    relation_scores: {out['relation_scores']}")
        if out.get("nucleus_resolved") and out["nucleus_resolved"] != c["nucleus"]:
            print(f"    nucleus anaphora-resolved: {out['nucleus_resolved']!r}")

    n_pass = sum(r["correct"] for r in results)
    print(f"\n{n_pass}/{len(results)} passed")
    json.dump(results, open("results/pipeline_v2_validation_report.json", "w"), indent=2)


if __name__ == "__main__":
    main()
